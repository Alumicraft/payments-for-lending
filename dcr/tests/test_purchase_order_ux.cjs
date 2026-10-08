const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const registered = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../public/js/purchase_order_ux.js"), "utf8"), {
    frappe: { ui: { form: { on: (name, callbacks) => { registered[name] = callbacks; } } } },
    erpnext: { get_currency: () => "USD" },
    __: value => value
});
const handlers = registered["Purchase Order"];
const childHandlers = registered["Purchase Order Item Supplied"];
function form(doc, extra = []) {
    const fields = [
        { fieldname: "supplier_section", fieldtype: "Section Break", label: "Supplier" },
        { fieldname: "supplier", fieldtype: "Link", label: "Supplier", reqd: 1 },
        { fieldname: "scan_barcode", fieldtype: "Data", hidden: 0 },
        { fieldname: "base_total_taxes_and_charges", fieldtype: "Currency", read_only: 1, hidden: 0, depends_on: "base_total_taxes_and_charges" },
        { fieldname: "in_words", fieldtype: "Data", read_only: 1, hidden: 0 },
        { fieldname: "raw_material_details", fieldtype: "Section Break", hidden: 0 },
        { fieldname: "supplied_items", fieldtype: "Table", hidden: 0 },
        ...extra,
        { fieldname: "items_section", fieldtype: "Section Break", label: "Items" }
    ];
    return { doc: { doctype: "Purchase Order", ...doc }, meta: { fields }, fields_dict: Object.fromEntries(fields.map(df => [df.fieldname, { df }])),
        set_df_property(name, property, value) { this.fields_dict[name].df[property] = value; },
        set_value() { throw new Error("Opening a saved order must not write data"); },
        dirty() { throw new Error("Opening a saved order must not dirty it"); }
    };
}
for (const docstatus of [0, 1, 2]) {
    const doc = { docstatus, custom_home_build_request: "HBR-A", supplied_items: [] };
    const frm = form(doc);
    const before = JSON.stringify(frm.doc);
    handlers.refresh(frm);
    assert.equal(frm.fields_dict.supplier.df.label, "Factory");
    assert.equal(frm.fields_dict.raw_material_details.df.hidden, 1);
    assert.equal(frm.fields_dict.supplied_items.df.hidden, 1);
    assert.equal(frm.fields_dict.scan_barcode.df.hidden, 1);
    handlers.refresh(frm);
    assert.equal(JSON.stringify(frm.doc), before);
    frm.doc.is_subcontracted = 1;
    handlers.is_subcontracted(frm);
    assert.equal(frm.fields_dict.raw_material_details.df.hidden, 0);
    frm.doc.is_subcontracted = 0;
    frm.doc.supplied_items = [{ item_code: "Existing material" }];
    childHandlers.supplied_items_add(frm);
    assert.equal(frm.fields_dict.supplied_items.df.hidden, 0);
    frm.doc.supplied_items = [];
    childHandlers.supplied_items_remove(frm);
    assert.equal(frm.fields_dict.supplied_items.df.hidden, 1);
    frm.doc.supplied_items = [{ item_code: "Existing material" }];
    handlers.supplied_items(frm);
    assert.equal(frm.fields_dict.supplied_items.df.hidden, 0);
    frm.doc.custom_home_build_request = null;
    handlers.custom_home_build_request(frm);
    assert.equal(frm.fields_dict.supplier.df.label, "Supplier");
    assert.equal(frm.fields_dict.scan_barcode.df.hidden, 0);
    frm.fields_dict.raw_material_details.df.hidden = 1;
    handlers.refresh(frm);
    assert.equal(frm.fields_dict.raw_material_details.df.hidden, 1, "Native visibility remains owned by ERPNext after leaving home scope");
}
const ordinary = form({ supplied_items: [] });
handlers.refresh(ordinary);
assert.equal(ordinary.fields_dict.supplier.df.label, "Supplier");
assert.equal(ordinary.fields_dict.raw_material_details.df.hidden, 0);
const details = form({ custom_home_build_request: "HBR-A" }, [
    { fieldname: "section_addresses", fieldtype: "Section Break", label: "Supplier Address" },
    { fieldname: "items", fieldtype: "Table", label: "Items" },
    { fieldname: "contact_email", fieldtype: "Data", read_only: 1, hidden: 0 },
    { fieldname: "contact_person", fieldtype: "Link", hidden: 0 }
]);
details.fields_dict.section_addresses.set_label = function (label) { this.renderedLabel = label; };
handlers.refresh(details);
assert.equal(details.fields_dict.section_addresses.renderedLabel, "Factory Address", "Section refresh alone does not render a changed label in v16");
assert.equal(details.fields_dict.items.df.label, "Homes");
assert.equal(details.fields_dict.contact_email.df.hidden, 1);
assert.equal(details.fields_dict.contact_person.df.hidden, 0, "Keep the selector usable when derived contact outputs are empty");
details.doc.contact_email = "factory@example.test";
handlers.contact_email(details);
assert.equal(details.fields_dict.contact_email.df.hidden, 0, "Fetched contact values must become visible without reopening the form");
details.doc.contact_email = "";
details.fields_dict.contact_email.df.reqd = 1;
handlers.refresh(details);
assert.equal(details.fields_dict.contact_email.df.hidden, 0, "Required fields remain usable");
details.doc.custom_home_build_request = null;
handlers.custom_home_build_request(details);
assert.equal(details.fields_dict.section_addresses.renderedLabel, "Supplier Address");
assert.equal(details.fields_dict.items.df.label, "Items");
const customized = form({ custom_home_build_request: "HBR-A" }, [{ fieldname: "custom_required_material_note", fieldtype: "Data", reqd: 1 }]);
handlers.refresh(customized);
assert.equal(customized.fields_dict.raw_material_details.df.hidden, 0, "Keep site-specific section inputs visible");
for (const property of ["reqd", "mandatory_depends_on"]) {
    const required = form({ custom_home_build_request: "HBR-A" });
    required.fields_dict.supplied_items.df[property] = 1;
    handlers.refresh(required);
    assert.equal(required.fields_dict.raw_material_details.df.hidden, 0);
    assert.equal(required.fields_dict.supplied_items.df.hidden, 0);
}
const legacy = form({ custom_home_build_request: "HBR-A", is_old_subcontracting_flow: 1 });
handlers.refresh(legacy);
assert.equal(legacy.fields_dict.raw_material_details.df.hidden, 0);
const scanned = form({ custom_home_build_request: "HBR-A", scan_barcode: "Existing scan" });
handlers.refresh(scanned);
assert.equal(scanned.fields_dict.scan_barcode.df.hidden, 0);
const domestic = form({ custom_home_build_request: "HBR-A", docstatus: 1, company: "DCR", currency: "USD", base_total_taxes_and_charges: 7440, total_taxes_and_charges: 7440 });
handlers.refresh(domestic);
assert.equal(domestic.fields_dict.base_total_taxes_and_charges.df.hidden, 1);
assert.equal(domestic.fields_dict.base_total_taxes_and_charges.df.depends_on, "eval:false", "Native dependency refresh must not reveal a hidden duplicate");
assert.equal(domestic.fields_dict.in_words.df.hidden, 1);
domestic.doc.currency = "EUR";
handlers.refresh(domestic);
assert.equal(domestic.fields_dict.base_total_taxes_and_charges.df.hidden, 0, "Keep company-currency totals when currencies differ");
assert.equal(domestic.fields_dict.base_total_taxes_and_charges.df.depends_on, "base_total_taxes_and_charges", "Restore the native visibility rule outside duplicate scope");
domestic.doc.currency = "USD";
domestic.doc.base_total_taxes_and_charges = 7441;
handlers.refresh(domestic);
assert.equal(domestic.fields_dict.base_total_taxes_and_charges.df.hidden, 0, "Never hide a discrepant total");
domestic.doc.base_total_taxes_and_charges = 7440;
domestic.doc.docstatus = 0;
handlers.refresh(domestic);
assert.equal(domestic.fields_dict.base_total_taxes_and_charges.df.hidden, 0, "Keep draft totals inspectable while pricing changes");
childHandlers.supplied_items_add({ doc: { doctype: "Another Parent" } });
console.log("Purchase Order UX: home scope, draft/submitted/cancelled, required/custom fields, materials, restoration and no document writes passed");
