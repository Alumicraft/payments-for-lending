frappe.ui.form.on('Loan Disbursement', {
    against_loan: function(frm) {
        if (!frm.doc.against_loan) return;

        frappe.db.get_value('Loan', frm.doc.against_loan, ['home_build_request'])
            .then(r => {
                if (!r.message) return;
                var hbr = r.message.home_build_request;
                if (hbr) {
                    frm.set_value('home_build_request', hbr);
                    frappe.db.get_value('Home Build Request', hbr, ['factory'])
                        .then(r2 => {
                            if (r2.message && r2.message.factory) {
                                frm.set_value('factory', r2.message.factory);
                            }
                        });
                }
            });
    }
});
