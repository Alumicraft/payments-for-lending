frappe.ui.form.on('Sales Invoice', {
    refresh(frm) {
        const ignored = frm.ignore_doctypes_on_cancel_all || [];
        if (frm.doc.__onload?.dcr_cancel_charge_demands_with_invoice) {
            if (!ignored.includes('Loan Demand')) {
                frm.ignore_doctypes_on_cancel_all = [...ignored, 'Loan Demand'];
                frm.__dcr_ignores_charge_demands = true;
            }
        } else if (frm.__dcr_ignores_charge_demands) {
            frm.ignore_doctypes_on_cancel_all = ignored.filter(name => name !== 'Loan Demand');
            delete frm.__dcr_ignores_charge_demands;
        }
    }
});
