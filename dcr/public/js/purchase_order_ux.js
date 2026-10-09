/* Presentation for home orders. Values and ERPNext business rules stay owned
 * by their existing controllers; this script never writes document data. */
(function () {
    var labels = {
        supplier: "Factory",
        supplier_name: "Factory Name",
        transaction_date: "Order Date",
        items: "Homes",
        section_addresses: "Factory Address",
        supplier_address: "Factory Address",
        address_display: "Factory Address Details",
        contact_person: "Factory Contact"
    };

    function known_section_fields(frm, section_name, names) {
        var fields = (frm.meta && frm.meta.fields) || [];
        var start = fields.findIndex(function (df) { return df.fieldname === section_name; });
        if (start < 0) return null;
        var end = fields.findIndex(function (df, index) {
            return index > start && ["Section Break", "Tab Break"].includes(df.fieldtype);
        });
        var contents = fields.slice(start + 1, end < 0 ? fields.length : end);
        if (!contents.length || !contents.every(function (df) {
            return df.fieldtype === "Column Break" || names.includes(df.fieldname);
        })) return null;
        return contents.filter(function (df) { return df.fieldtype !== "Column Break"; });
    }

    function hide_empty_section(frm, overrides, section_name, names) {
        var contents = known_section_fields(frm, section_name, names);
        if (contents && contents.length && contents.every(function (df) {
            return overrides[df.fieldname] && overrides[df.fieldname].hidden;
        })) overrides[section_name] = { hidden: 1 };
    }

    function apply_layout(frm) {
        var home_order = Boolean(frm.doc.custom_home_build_request);
        var state = frm.__dcr_po_layout || (frm.__dcr_po_layout = {});
        var overrides = {};
        if (home_order) {
            Object.keys(labels).forEach(function (name) {
                overrides[name] = { label: __(labels[name]) };
            });
            // These values are derived from the selected contact/address or
            // upstream documents. Empty outputs add no information; keep the
            // editable selectors and any required or populated values.
            ["contact_display", "contact_mobile", "contact_email", "address_display",
                "dispatch_address_display", "shipping_address_display", "billing_address_display",
                "represents_company", "ref_sq", "mps", "inter_company_order_reference"].forEach(function (name) {
                var field = frm.fields_dict[name];
                if (field && field.df.read_only && !field.df.reqd &&
                        !field.df.mandatory_depends_on && !frm.doc[name]) {
                    overrides[name] = Object.assign({}, overrides[name], { hidden: 1 });
                }
            });
            // A submitted/cancelled order cannot use blank immutable selectors.
            // Keep draft inputs, staff-editable fields and populated references.
            if (frm.doc.docstatus > 0) {
                ["contact_person", "shipping_address", "billing_address",
                    "payment_terms_template", "tc_name", "terms", "tax_category",
                    "shipping_rule", "incoterm", "taxes_and_charges"].forEach(function (name) {
                    var field = frm.fields_dict[name];
                    if (field && !field.df.allow_on_submit && !field.df.reqd &&
                            !field.df.mandatory_depends_on && !frm.doc[name]) {
                        overrides[name] = { hidden: 1 };
                    }
                });
                hide_empty_section(frm, overrides, "company_billing_address_section",
                    ["billing_address", "billing_address_display"]);
                hide_empty_section(frm, overrides, "terms_section_break", ["tc_name", "terms"]);
                // A blank header warehouse has no bulk-entry purpose on a
                // saved ordinary home order. Row warehouse values stay visible.
                var warehouse = frm.fields_dict.set_warehouse;
                if (!frm.doc.is_subcontracted && !frm.doc.is_old_subcontracting_flow &&
                        warehouse && !warehouse.df.allow_on_submit && !warehouse.df.reqd &&
                        !warehouse.df.mandatory_depends_on && !frm.doc.set_warehouse) {
                    overrides.set_warehouse = { hidden: 1 };
                }
            }
            // Home purchases do not repeat automatically. When no repeat or
            // dates exist, remove the unused group, including its heading.
            // A site field, populated value or required input retains the group.
            var repeat_names = ["from_date", "to_date", "auto_repeat", "update_auto_repeat_reference"];
            var repeat_fields = known_section_fields(frm, "auto_repeat_section", repeat_names);
            if (!frm.doc.is_subcontracted && !frm.doc.is_old_subcontracting_flow &&
                    repeat_fields && repeat_fields.length && repeat_fields.every(function (df) {
                        return !df.reqd && !df.mandatory_depends_on && !frm.doc[df.fieldname];
                    })) {
                repeat_fields.forEach(function (df) { overrides[df.fieldname] = { hidden: 1 }; });
                overrides.auto_repeat_section = { hidden: 1 };
            }
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
            // An unchanged rounded total repeats the grand total. Keep both
            // when rounding differs, while editing, or when a site requires it.
            var grand = frm.doc.grand_total;
            var rounded = frm.doc.rounded_total;
            var adjustment = frm.doc.rounding_adjustment;
            if (frm.doc.docstatus > 0 && grand != null && grand !== "" &&
                    rounded != null && rounded !== "" && adjustment != null && adjustment !== "" &&
                    Number.isFinite(Number(grand)) && Number.isFinite(Number(rounded)) &&
                    Number(grand) === Number(rounded) && Number(adjustment) === 0) {
                ["rounded_total", "rounding_adjustment"].forEach(function (name) {
                    var field = frm.fields_dict[name];
                    if (field && field.df.fieldtype === "Currency" && field.df.read_only &&
                            !field.df.allow_on_submit && !field.df.reqd && !field.df.mandatory_depends_on) {
                        overrides[name] = { hidden: 1 };
                    }
                });
            }
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
                    // Frappe v16 Section.refresh only changes visibility. Its
                    // native label method updates an existing section heading.
                    if (property === "label" && field.df.fieldtype === "Section Break" &&
                            !field.df.collapsible && typeof field.set_label === "function") {
                        field.set_label(value);
                    }
                    // Grid.make creates its own label once; ControlTable's
                    // refresh only refreshes rows. Update that grid-owned label
                    // without touching columns, row editors, focus or values.
                    if (property === "label" && field.df.fieldtype === "Table" &&
                            field.grid && field.grid.wrapper) {
                        field.grid.wrapper.children("label.control-label").text(value);
                    }
                    if (property === "depends_on") dependencies_changed = true;
                }
                if (!Object.prototype.hasOwnProperty.call(properties, property)) delete original[property];
            });
            if (!Object.keys(original).length) delete state[name];
        });
        if (dependencies_changed && frm.layout && frm.layout.refresh_dependency) frm.layout.refresh_dependency();
        apply_item_layout(frm);
    }

    function apply_item_layout(frm) {
        if (frm.doc.doctype !== "Purchase Order") return;
        var grid = frm.fields_dict.items && frm.fields_dict.items.grid;
        if (!grid) return;
        var visible_columns = (grid.visible_columns || []).map(function (column) { return column[0].fieldname; });
        var home_order = Boolean(frm.doc.custom_home_build_request) &&
            !frm.doc.is_subcontracted && !frm.doc.is_old_subcontracting_flow;
        var company_currency = frm.doc.company && typeof erpnext !== "undefined" && erpnext.get_currency
            ? erpnext.get_currency(frm.doc.company) : null;
        (grid.grid_rows || []).forEach(function (row) {
            // Work with the row editor's own controls, never shared child
            // DocType metadata or another parent's table/column settings.
            var editor = row.grid_form;
            if (!editor || !editor.fields_dict || !row.doc) return;
            var state = row.__dcr_home_item_layout || (row.__dcr_home_item_layout = {});
            var overrides = {};
            var empty_fields = ["product_bundle", "production_plan", "job_card",
                "weight_per_unit", "total_weight", "weight_uom",
                "manufacturer", "manufacturer_part_no", "bom", "include_exploded_items"];
            if (home_order) {
                empty_fields.forEach(function (name) {
                    var field = editor.fields_dict[name];
                    var value = row.doc[name];
                    if (field && !visible_columns.includes(name) && !field.df.reqd && !field.df.mandatory_depends_on &&
                            (value == null || value === "" || value === 0 || value === false)) {
                        overrides[name] = 1;
                    }
                });
                // Required base rate/amount fields can be suppressed only on
                // immutable records with their stored calculations verified.
                // Drafts and any discrepancy retain both currency values.
                if (frm.doc.docstatus > 0 && company_currency && company_currency === frm.doc.currency) {
                    ["price_list_rate", "rate", "amount", "net_rate", "net_amount"].forEach(function (name) {
                        var base = "base_" + name;
                        var field = editor.fields_dict[base];
                        if (field && !visible_columns.includes(base) && field.df.read_only && !field.df.allow_on_submit &&
                                !field.df.mandatory_depends_on && row.doc[base] != null &&
                                row.doc[name] != null && Number.isFinite(Number(row.doc[base])) &&
                                Number(row.doc[base]) === Number(row.doc[name])) {
                            overrides[base] = 1;
                        }
                    });
                }
                ["manufacture_details", "item_weight_details"].forEach(function (name) {
                    var section = editor.layout && editor.layout.sections_dict && editor.layout.sections_dict[name];
                    // An extra site field keeps the section available.
                    if (section && section.fields_list && section.fields_list.length &&
                            section.fields_list.every(function (field) {
                                return empty_fields.includes(field.df.fieldname) && overrides[field.df.fieldname] === 1;
                            })) overrides[name] = 1;
                });
            }
            Array.from(new Set(Object.keys(state).concat(Object.keys(overrides)))).forEach(function (name) {
                var field = editor.fields_dict[name] ||
                    (editor.layout && editor.layout.sections_dict && editor.layout.sections_dict[name]);
                if (!field) return;
                if (!Object.prototype.hasOwnProperty.call(state, name)) state[name] = field.df.hidden;
                var hidden = Object.prototype.hasOwnProperty.call(overrides, name) ? overrides[name] : state[name];
                if (field.df.hidden !== hidden) {
                    if (field.df.fieldtype === "Section Break") {
                        field.df.hidden = hidden;
                        field.refresh();
                    } else field.toggle(!hidden);
                }
                if (!Object.prototype.hasOwnProperty.call(overrides, name)) delete state[name];
            });
            // Native columns do not shrink when their individual controls
            // disappear. Collapse only columns wholly suppressed by this
            // profile; unknown controls and column headings retain their space.
            var column_state = row.__dcr_home_item_columns || (row.__dcr_home_item_columns = new Map());
            var sections = (editor.layout && editor.layout.sections_dict) || {};
            Object.keys(sections).forEach(function (name) {
                var section = sections[name];
                (section.columns || []).forEach(function (column) {
                    if (!column.df || !column.form || typeof column.form.get !== "function" ||
                            typeof column.refresh !== "function") return;
                    var parent = column.form.get(0);
                    var contents = (section.fields_list || []).filter(function (field) {
                        return field.parent === parent;
                    });
                    var suppressed_field = function (field) { return overrides[field.df.fieldname] === 1; };
                    var native_hidden_pricing = function (field) {
                        // These native calculations live beside base amounts.
                        // Respect their existing visibility; never hide them.
                        return frm.doc.docstatus > 0 &&
                            ["pricing_rules", "stock_uom_rate", "is_free_item"].includes(field.df.fieldname) &&
                            field.df.read_only && !field.df.reqd && !field.df.mandatory_depends_on &&
                            !field.df.allow_on_submit && (field.df.hidden || field.df.hidden_due_to_dependency);
                    };
                    var suppress = home_order && !column.df.label && !column.df.description &&
                        contents.some(suppressed_field) && contents.every(function (field) {
                            return suppressed_field(field) || native_hidden_pricing(field);
                        });
                    if (suppress && !column_state.has(column)) column_state.set(column, column.df.hidden);
                    if (!column_state.has(column)) return;
                    var hidden = suppress ? 1 : column_state.get(column);
                    if (column.df.hidden !== hidden) {
                        column.df.hidden = hidden;
                        // Refresh uses Frappe's own direct-child column sizing.
                        column.refresh();
                    }
                    if (!suppress) column_state.delete(column);
                });
            });
            Object.keys(sections).forEach(function (name) {
                var section = sections[name];
                var columns = section.columns || [];
                var visible = columns.filter(function (column) {
                    return column.df && !column.df.hidden && !column.df.hidden_due_to_dependency;
                });
                var reclaimed = columns.some(function (column) { return column_state.has(column); });
                columns.forEach(function (column) {
                    if (!column.form || typeof column.form.toggleClass !== "function") return;
                    var parent = column.form.get(0);
                    var names = (section.fields_list || []).filter(function (field) {
                        return field.parent === parent;
                    }).map(function (field) { return field.df.fieldname; }).join(",");
                    var pair = ["price_list_rate,last_purchase_rate", "net_rate,net_amount",
                        "rate,amount,item_tax_template"].includes(names);
                    column.form.toggleClass("dcr-home-pricing-fields", Boolean(home_order && reclaimed &&
                        visible.length === 1 && visible[0] === column && !column.df.label &&
                        !column.df.description && pair));
                });
            });
            if (editor.layout && editor.layout.refresh_sections) editor.layout.refresh_sections();
        });
    }

    frappe.ui.form.on("Purchase Order", {
        refresh: apply_layout,
        custom_home_build_request: apply_layout,
        is_subcontracted: apply_layout,
        is_old_subcontracting_flow: apply_layout,
        company: apply_layout,
        currency: apply_layout,
        contact_person: apply_layout,
        supplier_address: apply_layout,
        dispatch_address: apply_layout,
        shipping_address: apply_layout,
        billing_address: apply_layout,
        contact_display: apply_layout,
        contact_mobile: apply_layout,
        contact_email: apply_layout,
        address_display: apply_layout,
        dispatch_address_display: apply_layout,
        shipping_address_display: apply_layout,
        billing_address_display: apply_layout,
        items_on_form_rendered: apply_item_layout,
        payment_terms_template: apply_layout,
        tax_category: apply_layout,
        shipping_rule: apply_layout,
        incoterm: apply_layout,
        taxes_and_charges: apply_layout,
        set_warehouse: apply_layout,
        tc_name: apply_layout,
        terms: apply_layout,
        from_date: apply_layout,
        to_date: apply_layout,
        auto_repeat: apply_layout,
        supplied_items: apply_layout
    });
    var item_handlers = {};
    ["product_bundle", "production_plan", "job_card", "weight_per_unit", "total_weight", "weight_uom",
        "manufacturer", "manufacturer_part_no", "bom", "include_exploded_items",
        "pricing_rules", "stock_uom_rate", "is_free_item"].forEach(function (name) {
        item_handlers[name] = apply_item_layout;
    });
    frappe.ui.form.on("Purchase Order Item", item_handlers);
    // Frappe dispatches grid add/remove events to the child DocType.
    function materials_changed(frm) {
        if (frm.doc.doctype === "Purchase Order") apply_layout(frm);
    }
    frappe.ui.form.on("Purchase Order Item Supplied", {
        supplied_items_add: materials_changed,
        supplied_items_remove: materials_changed
    });
})();
