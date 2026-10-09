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
        if (frm.layout && frm.layout.refresh_dependency) frm.layout.refresh_dependency();
    }

    ["Loan", "Loan Application"].forEach(function (doctype) {
        frappe.ui.form.on(doctype, {
            refresh: apply_forecast_visibility,
            home_build_request: apply_forecast_visibility
        });
    });
})();
