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
details.fields_dict.items.grid = { wrapper: { children(selector) {
    assert.equal(selector, "label.control-label", "Only the grid's own heading is updated");
    return { text(label) { details.fields_dict.items.renderedLabel = label; } };
} } };
handlers.refresh(details);
assert.equal(details.fields_dict.section_addresses.renderedLabel, "Factory Address", "Section refresh alone does not render a changed label in v16");
assert.equal(details.fields_dict.items.df.label, "Homes");
assert.equal(details.fields_dict.items.renderedLabel, "Homes", "ControlTable refresh does not update the rendered grid heading");
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
assert.equal(details.fields_dict.items.renderedLabel, "Items");
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
function itemForm(status = 1) {
    const frm = form({ docstatus: status, company: "DCR", currency: "USD", custom_home_build_request: "HBR-A" },
        [{ fieldname: "items", fieldtype: "Table", label: "Items" }]);
    const fields = [
        { fieldname: "base_rate", fieldtype: "Currency", read_only: 1, reqd: 1 },
        { fieldname: "base_amount", fieldtype: "Currency", read_only: 1, reqd: 1 },
        { fieldname: "rate", fieldtype: "Currency", reqd: 1 },
        { fieldname: "qty", fieldtype: "Float", reqd: 1 },
        { fieldname: "warehouse", fieldtype: "Link", reqd: 1 },
        { fieldname: "manufacturer", fieldtype: "Link" },
        { fieldname: "manufacturer_part_no", fieldtype: "Data" },
        { fieldname: "bom", fieldtype: "Link", read_only: 1 },
        { fieldname: "include_exploded_items", fieldtype: "Check" }
    ].map(df => ({ df: { hidden: 0, ...df }, toggle(show) { this.df.hidden = show ? 0 : 1; } }));
    const section = { df: { fieldname: "manufacture_details", fieldtype: "Section Break", hidden: 0 },
        fields_list: fields.slice(5), refresh() {} };
    const row = { doc: { rate: 120, base_rate: 120, amount: 120, base_amount: 120, qty: 1 },
        grid_form: { fields_dict: Object.fromEntries(fields.map(field => [field.df.fieldname, field])),
            layout: { sections_dict: { manufacture_details: section }, refresh_sections() {} } } };
    frm.fields_dict.items.grid = { grid_rows: [row], visible_columns: [[fields[2].df, 1], [fields[3].df, 1]] };
    return { frm, row, fields: row.grid_form.fields_dict, section };
}
for (const status of [0, 1, 2]) {
    const { frm, row, fields, section } = itemForm(status);
    const original = JSON.stringify(row.doc);
    handlers.items_on_form_rendered(frm);
    assert.equal(fields.base_rate.df.hidden, status > 0 ? 1 : 0, "Only verified immutable calculations may hide required base amounts");
    assert.equal(fields.rate.df.hidden, 0);
    assert.equal(fields.qty.df.hidden, 0);
    assert.equal(fields.warehouse.df.hidden, 0);
    assert.equal(section.df.hidden, 1);
    row.doc.manufacturer = "Populated manufacturer";
    registered["Purchase Order Item"].manufacturer(frm);
    assert.equal(fields.manufacturer.df.hidden, 0);
    assert.equal(section.df.hidden, 0);
    frm.doc.is_subcontracted = 1;
    handlers.is_subcontracted(frm);
    assert.equal(fields.manufacturer_part_no.df.hidden, 0);
    assert.equal(fields.base_rate.df.hidden, 0);
    frm.doc.is_subcontracted = 0;
    row.doc.manufacturer = "";
    frm.doc.custom_home_build_request = null;
    handlers.custom_home_build_request(frm);
    assert.equal(fields.manufacturer_part_no.df.hidden, 0);
    assert.equal(fields.base_amount.df.hidden, 0);
    assert.equal(JSON.stringify({ ...row.doc, manufacturer: undefined }), original);
}
const rowMismatch = itemForm();
rowMismatch.row.doc.base_rate = 121;
handlers.items_on_form_rendered(rowMismatch.frm);
assert.equal(rowMismatch.fields.base_rate.df.hidden, 0);
rowMismatch.frm.doc.currency = "EUR";
handlers.currency(rowMismatch.frm);
assert.equal(rowMismatch.fields.base_amount.df.hidden, 0);
const customizedRow = itemForm();
customizedRow.section.fields_list.push({ df: { fieldname: "custom_note", hidden: 0 } });
customizedRow.fields.manufacturer.df.mandatory_depends_on = "eval:doc.qty";
customizedRow.fields.base_rate.df.allow_on_submit = 1;
customizedRow.frm.fields_dict.items.grid.visible_columns.push([customizedRow.fields.base_amount.df, 1]);
handlers.items_on_form_rendered(customizedRow.frm);
assert.equal(customizedRow.section.df.hidden, 0, "Site fields keep their section available");
assert.equal(customizedRow.fields.manufacturer.df.hidden, 0);
assert.equal(customizedRow.fields.base_rate.df.hidden, 0);
assert.equal(customizedRow.fields.base_amount.df.hidden, 0, "Preserve user-configured grid columns");
// A suppressed base-currency column must release its reserved width. Keep
// columns containing any other field, heading or site customization intact.
function columnFixture(status = 1) {
    const fixture = itemForm(status);
    const parent = {};
    fixture.fields.base_rate.parent = parent;
    fixture.fields.base_amount.parent = parent;
    const column = { df: { fieldname: "base_currency_column", fieldtype: "Column Break", hidden: 0 },
        form: { get() { return parent; } }, refreshes: 0,
        refresh() { this.refreshes++; this.renderedHidden = Boolean(this.df.hidden); } };
    const section = { df: { fieldname: "amounts" },
        fields_list: [fixture.fields.base_rate, fixture.fields.base_amount], columns: [column] };
    fixture.row.grid_form.layout.sections_dict.amounts = section;
    return { ...fixture, column, amountSection: section };
}
for (const status of [0, 1, 2]) {
    const fixture = columnFixture(status);
    const before = JSON.stringify(fixture.row.doc);
    handlers.items_on_form_rendered(fixture.frm);
    assert.equal(fixture.column.df.hidden, status > 0 ? 1 : 0,
        "Hide only a column whose complete contents are verified suppressed fields");
    if (status > 0) assert.equal(fixture.column.renderedHidden, true);
    fixture.row.doc.base_rate = 121;
    handlers.items_on_form_rendered(fixture.frm);
    assert.equal(fixture.column.df.hidden, 0, "A discrepancy restores the column and its original width");
    fixture.row.doc.base_rate = 120;
    handlers.items_on_form_rendered(fixture.frm);
    fixture.frm.doc.custom_home_build_request = null;
    handlers.custom_home_build_request(fixture.frm);
    assert.equal(fixture.column.df.hidden, 0, "Restore native columns on scope exit");
    assert.equal(JSON.stringify(fixture.row.doc), before);
}
for (const extra of ["field", "label", "description"]) {
    const fixture = columnFixture();
    if (extra === "field") fixture.amountSection.fields_list.push({
        df: { fieldname: "custom_note", hidden: 1 }, parent: fixture.fields.base_rate.parent
    });
    else fixture.column.df[extra] = "Site context";
    handlers.items_on_form_rendered(fixture.frm);
    assert.equal(fixture.column.df.hidden, 0, "Preserve site column content even when it is currently hidden");
}
const nativeHiddenColumn = columnFixture();
nativeHiddenColumn.column.df.hidden = 1;
handlers.items_on_form_rendered(nativeHiddenColumn.frm);
nativeHiddenColumn.frm.doc.is_subcontracted = 1;
handlers.is_subcontracted(nativeHiddenColumn.frm);
assert.equal(nativeHiddenColumn.column.df.hidden, 1, "Preserve an originally hidden column");
console.log("Purchase Order UX: home scope, draft/submitted/cancelled, required/custom fields, materials, restoration and no document writes passed");
