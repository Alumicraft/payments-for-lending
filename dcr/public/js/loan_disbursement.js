frappe.ui.form.on('Loan Disbursement', {
    onload_post_render: function(frm) {
        if (frm.doc.against_loan && !frm.doc.home_build_request) {
            fetch_deal_reference(frm);
        }
    },

    against_loan: function(frm) {
        if (frm.doc.against_loan) {
            fetch_deal_reference(frm);
        }
    }
});

function fetch_deal_reference(frm) {
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
