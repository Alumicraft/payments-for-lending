const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const registered = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../public/js/purchase_order_ux.js"), "utf8"), {
    frappe: { ui: { form: { on: (name, callbacks) => { registered[name] = callbacks; } } } },
    __: value => value
});
const handlers = registered["Purchase Order"];
const childHandlers = registered["Purchase Order Item Supplied"];
function form(doc, extra = []) {
    const fields = [
        { fieldname: "supplier_section", fieldtype: "Section Break", label: "Supplier" },
        { fieldname: "supplier", fieldtype: "Link", label: "Supplier", reqd: 1 },
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
    frm.fields_dict.raw_material_details.df.hidden = 1;
    handlers.refresh(frm);
    assert.equal(frm.fields_dict.raw_material_details.df.hidden, 1, "Native visibility remains owned by ERPNext after leaving home scope");
}
const ordinary = form({ supplied_items: [] });
handlers.refresh(ordinary);
assert.equal(ordinary.fields_dict.supplier.df.label, "Supplier");
assert.equal(ordinary.fields_dict.raw_material_details.df.hidden, 0);
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
childHandlers.supplied_items_add({ doc: { doctype: "Another Parent" } });
console.log("Purchase Order UX: home scope, draft/submitted/cancelled, required/custom fields, materials, restoration and no document writes passed");
