/* Presentation for home orders. Values and ERPNext business rules stay owned
 * by their existing controllers; this script never writes document data. */
(function () {
    var labels = {
        supplier_section: "Dealer and Factory",
        supplier: "Factory",
        supplier_name: "Factory Name",
        transaction_date: "Order Date",
        items_section: "Homes",
        section_addresses: "Factory Address",
        supplier_address: "Factory Address",
        contact_person: "Factory Contact"
    };

    function apply_layout(frm) {
        var home_order = Boolean(frm.doc.custom_home_build_request);
        var state = frm.__dcr_po_layout || (frm.__dcr_po_layout = {});
        var overrides = {};
        if (home_order) {
            Object.keys(labels).forEach(function (name) {
                overrides[name] = { label: __(labels[name]) };
            });
            // Barcode scanning serves warehouse purchasing, not a home order.
            // Keep any populated or site-required inputs inspectable.
            ["scan_barcode", "last_scanned_warehouse"].forEach(function (name) {
                var field = frm.fields_dict[name];
                if (field && !field.df.reqd && !field.df.mandatory_depends_on && !frm.doc[name]) {
                    overrides[name] = { hidden: 1 };
                }
            });
            // The numeric totals are the useful order summary. Preserve the
            // stored wording for printing without repeating it in the form.
            ["in_words", "base_in_words"].forEach(function (name) {
                var field = frm.fields_dict[name];
                if (field && field.df.read_only && !field.df.reqd && !field.df.mandatory_depends_on) {
                    overrides[name] = { hidden: 1 };
                }
            });
            var company_currency = frm.doc.company && typeof erpnext !== "undefined" && erpnext.get_currency
                ? erpnext.get_currency(frm.doc.company) : null;
            // Amounts on submitted/cancelled orders are immutable. Drafts keep
            // both totals available while currency and pricing are being edited.
            if (frm.doc.docstatus > 0 && company_currency && company_currency === frm.doc.currency) {
                ["total", "net_total", "taxes_and_charges_added", "taxes_and_charges_deducted",
                    "total_taxes_and_charges", "grand_total", "rounding_adjustment", "rounded_total"].forEach(function (name) {
                    var base_name = "base_" + name;
                    var field = frm.fields_dict[base_name];
                    if (field && field.df.read_only && !field.df.reqd && !field.df.mandatory_depends_on &&
                            frm.doc[base_name] != null && frm.doc[name] != null &&
                            Number(frm.doc[base_name]) === Number(frm.doc[name])) {
                        overrides[base_name] = { hidden: 1 };
                    }
                });
            }
            // Existing materials or either subcontracting flow must remain
            // inspectable, including on submitted and cancelled orders.
            if (!frm.doc.is_subcontracted && !frm.doc.is_old_subcontracting_flow &&
                    !(frm.doc.supplied_items || []).length) {
                var materials = frm.fields_dict.supplied_items;
                if (materials && !materials.df.reqd && !materials.df.mandatory_depends_on) {
                    overrides.supplied_items = { hidden: 1 };
                    // Site customizations may put other inputs in this section.
                    // Hide the whole section only when its contents are known.
                    var fields = (frm.meta && frm.meta.fields) || [];
                    var start = fields.findIndex(function (df) { return df.fieldname === "raw_material_details"; });
                    if (start >= 0) {
                        var end = fields.findIndex(function (df, index) {
                            return index > start && ["Section Break", "Tab Break"].includes(df.fieldtype);
                        });
                        var contents = fields.slice(start + 1, end < 0 ? fields.length : end);
                        if (contents.every(function (df) {
                            return df.fieldname === "supplied_items" || df.fieldtype === "Column Break";
                        })) overrides.raw_material_details = { hidden: 1 };
                    }
                }
            }
        }
        // ERPNext's currency-label refresh can toggle populated base tax
        // totals back on after our refresh handler. Keep their dependency
        // false while suppressed, then restore the native rule on scope exit.
        Object.keys(overrides).forEach(function (name) {
            var field = frm.fields_dict[name];
            if (overrides[name].hidden && field && field.df.depends_on) {
                overrides[name].depends_on = "eval:false";
            }
        });
        var dependencies_changed = false;
        Array.from(new Set(Object.keys(state).concat(Object.keys(overrides)))).forEach(function (name) {
            var field = frm.fields_dict[name];
            if (!field) return;
            var properties = overrides[name] || {};
            var original = state[name] || (state[name] = {});
            Array.from(new Set(Object.keys(original).concat(Object.keys(properties)))).forEach(function (property) {
                if (!Object.prototype.hasOwnProperty.call(original, property)) {
                    original[property] = field.df[property];
                }
                var value = Object.prototype.hasOwnProperty.call(properties, property)
                    ? properties[property] : original[property];
                if (field.df[property] !== value) {
                    frm.set_df_property(name, property, value);
                    if (property === "depends_on") dependencies_changed = true;
                }
                if (!Object.prototype.hasOwnProperty.call(properties, property)) delete original[property];
            });
            if (!Object.keys(original).length) delete state[name];
        });
        if (dependencies_changed && frm.layout && frm.layout.refresh_dependency) frm.layout.refresh_dependency();
    }

    frappe.ui.form.on("Purchase Order", {
        refresh: apply_layout,
        custom_home_build_request: apply_layout,
        is_subcontracted: apply_layout,
        is_old_subcontracting_flow: apply_layout,
        company: apply_layout,
        currency: apply_layout,
        supplied_items: apply_layout
    });
    // Frappe dispatches grid add/remove events to the child DocType.
    function materials_changed(frm) {
        if (frm.doc.doctype === "Purchase Order") apply_layout(frm);
    }
    frappe.ui.form.on("Purchase Order Item Supplied", {
        supplied_items_add: materials_changed,
        supplied_items_remove: materials_changed
    });
})();
