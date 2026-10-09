/* Fixed-term forecasts are not balances due on home-financing documents.
 * Keep their stored calculations for existing controllers and print formats;
 * presentation changes must never write financial values. */
(function () {
    var forecast_fields = ["total_payable_interest", "total_interest_payable",
        "total_payable_amount", "total_payment"];

    function apply_forecast_visibility(frm) {
        var state = frm.__dcr_flooring_forecast_visibility ||
            (frm.__dcr_flooring_forecast_visibility = {});
        forecast_fields.forEach(function (name) {
            var field = frm.fields_dict[name];
            if (!field) return;
            var suppress = Boolean(frm.doc.home_build_request &&
                field.df.fieldtype === "Currency" && field.df.read_only &&
                !field.df.reqd && !field.df.mandatory_depends_on);
            if (suppress && !Object.prototype.hasOwnProperty.call(state, name)) {
                state[name] = { hidden: field.df.hidden, depends_on: field.df.depends_on };
            }
            if (!Object.prototype.hasOwnProperty.call(state, name)) return;
            var properties = suppress ? { hidden: 1, depends_on: "eval:false" } : state[name];
            Object.keys(properties).forEach(function (property) {
                if (field.df[property] !== properties[property]) {
                    frm.set_df_property(name, property, properties[property]);
                }
            });
            if (!suppress) delete state[name];
        });
        // Moving the payment out of credit limits must retain normal term-loan
        // visibility outside home financing. Never replace an unknown site rule.
        if (frm.doc.doctype === "Loan") {
            var payment = frm.fields_dict.monthly_repayment_amount;
            var payment_state = frm.__dcr_monthly_payment_visibility;
            var native_rule = 'eval: doc.is_term_loan && doc.repayment_schedule_type != "Line of Credit"';
            var original_rule = payment_state ? payment_state.depends_on : payment && payment.df.depends_on;
            var show_payment = payment && frm.doc.home_build_request && !payment.df.hidden &&
                payment.df.fieldtype === "Currency" && (!original_rule || original_rule === native_rule);
            if (show_payment && !payment_state) {
                payment_state = frm.__dcr_monthly_payment_visibility = { depends_on: original_rule };
            }
            if (payment && payment_state) {
                var rule = show_payment ? "eval:true" : payment_state.depends_on;
                if (payment.df.depends_on !== rule) frm.set_df_property("monthly_repayment_amount", "depends_on", rule);
                if (!show_payment) delete frm.__dcr_monthly_payment_visibility;
            }
        }
        // Native columns keep their width after their fields disappear. Only
        // collapse columns wholly suppressed by this profile, retaining custom
        // controls, headings and the original native hidden state.
        var columns_state = frm.__dcr_forecast_columns || (frm.__dcr_forecast_columns = new Map());
        var sections = (frm.layout && frm.layout.sections_dict) || {};
        Object.keys(sections).forEach(function (name) {
            var section = sections[name];
            (section.columns || []).forEach(function (column) {
                if (!column.df || !column.form || typeof column.form.get !== "function" ||
                        typeof column.refresh !== "function") return;
                var parent = column.form.get(0);
                var contents = (section.fields_list || []).filter(function (field) { return field.parent === parent; });
                var suppress = frm.doc.home_build_request && !column.df.label && !column.df.description &&
                    contents.length && contents.every(function (field) {
                        return forecast_fields.includes(field.df.fieldname) && state[field.df.fieldname] &&
                            field.df.hidden && field.df.depends_on === "eval:false";
                    });
                if (suppress && !columns_state.has(column)) columns_state.set(column, column.df.hidden);
                if (!columns_state.has(column)) return;
                var hidden = suppress ? 1 : columns_state.get(column);
                if (column.df.hidden !== hidden) { column.df.hidden = hidden; column.refresh(); }
                if (!suppress) columns_state.delete(column);
            });
        });
        if (frm.layout && frm.layout.refresh_dependency) frm.layout.refresh_dependency();
    }

    ["Loan", "Loan Application"].forEach(function (doctype) {
        frappe.ui.form.on(doctype, {
            refresh: apply_forecast_visibility,
            home_build_request: apply_forecast_visibility
        });
    });
})();
