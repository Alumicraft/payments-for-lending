frappe.provide('dcr');

dcr.update_dated_loan_preview = function(frm, set_value) {
    if (frm.doc.docstatus && frm.doc.docstatus !== 0) return;
    var sequence = (frm.__dcr_preview_sequence || 0) + 1;
    frm.__dcr_preview_sequence = sequence;
    var name = frm.doc.name;
    var amount = frm.doc.doctype === 'Loan' && frm.fields_dict.qualifying_amount
        ? frm.doc.qualifying_amount : frm.doc.loan_amount;
    frappe.call({
        method: 'dcr.api.lending.get_dated_loan_preview',
        args: {
            doctype: frm.doc.doctype, loan_amount: amount || 0,
            rate_of_interest: frm.doc.rate_of_interest || 0,
            repayment_periods: frm.doc.repayment_periods || 0,
            projected_sales_price: frm.doc.custom_projected_sales_price || 0,
            interest_start_date: frm.doc.financed_invoice_date ||
                (frm.doc.doctype === 'Loan' && !frm.doc.loan_application ? frm.doc.posting_date : null),
            first_payment_date: frm.doc.first_payment_date || frm.doc.repayment_start_date || null,
            loan_application: frm.doc.loan_application || null,
            loan_product: frm.doc.loan_product || null
        },
        callback: function(r) {
            if (frm.doc.name !== name || frm.__dcr_preview_sequence !== sequence || frm.doc.docstatus) return;
            Object.keys(r.message || {}).forEach(function(field) {
                // The server derives the full schedule length. Updating the
                // native tenure here would retrigger its own payment formula.
                if (field !== 'repayment_periods') set_value(frm, field, r.message[field]);
            });
        }
    });
};
