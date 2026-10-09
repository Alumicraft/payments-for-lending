/**
 * Loan Form Customization
 *
 * Buttons:
 * - Email → "Disbursement Notice" — notify dealer of disbursement
 * - Email → "FL Payoff Letter" / "COD Payoff Letter" — payoff letters
 *
 * Indicators:
 * - Linked bank account (does not certify automatic debit activation)
 *
 * Auto-Pay setup email is sent automatically on save when no bank account
 * is linked (server-side, with 24-hour dedup).
 */

frappe.ui.form.on('Loan', {
    refresh: function(frm) {
        if (frm.is_new()) {
            ensure_loan_preview_defaults(frm);
            prefill_deal_reference(frm);
            calculate_loan_preview(frm);
            return;
        }

        // Linked bank account indicator (show on saved and submitted loans)
        show_autopay_indicator(frm);

        // Draft loans need the same visible preview as Loan Applications.
        // Submitted loans keep their server-authoritative totals untouched.
        calculate_loan_preview(frm);

        // Submitted-only buttons
        if (frm.doc.docstatus !== 1) {
            return;
        }

        // Email: Disbursement Notice
        frappe.db.count('Loan Disbursement', {
            filters: { against_loan: frm.doc.name, docstatus: 1 }
        }).then(count => {
            if (count > 0) {
                frm.add_custom_button(__('Disbursement Notice'), function() {
                    send_disbursement_notice(frm);
                }, __('Email'));
            }
        });

        // Email: Payoff letter buttons
        if (frm.doc.status && ['Disbursed', 'Active'].includes(frm.doc.status)) {
            frm.add_custom_button(__('FL Payoff Letter'), function() {
                send_payoff(frm, 'Flooring');
            }, __('Email'));

            frm.add_custom_button(__('COD Payoff Letter'), function() {
                send_payoff(frm, 'COD');
            }, __('Email'));
        }
    },

    loan_amount: function(frm) {
        calculate_loan_preview(frm);
    },

    qualifying_amount: function(frm) {
        calculate_loan_preview(frm);
    },

    rate_of_interest: function(frm) {
        calculate_loan_preview(frm);
    },

    repayment_periods: function(frm) {
        calculate_loan_preview(frm);
    },

    posting_date: function(frm) { calculate_loan_preview(frm); },
    repayment_start_date: function(frm) { calculate_loan_preview(frm); },
    loan_application: function(frm) { calculate_loan_preview(frm); },

    custom_projected_sales_price: function(frm) {
        calculate_loan_preview(frm);
    }
});


function ensure_loan_preview_defaults(frm) {
    // Twelve interest-only payments plus one hundred 1% reductions.
    // The server derives the actual row count once payment dates are known.
    if (!frm.doc.repayment_periods && frm.fields_dict.repayment_periods) {
        frm.set_value('repayment_periods', 112);
    }

    // Lending may carry the mapped principal in a hidden loan_amount field,
    // while DCR shows qualifying_amount. Keep the visible input aligned so
    // operators do not see $0 beside totals calculated from another value.
    if (!frm.doc.qualifying_amount && frm.doc.loan_amount && frm.fields_dict.qualifying_amount) {
        frm.set_value('qualifying_amount', frm.doc.loan_amount);
    }
}


function prefill_deal_reference(frm) {
    // When a new Loan form opens (from "Create Loan" on a Loan Application),
    // fill in deal-reference fields right away so the user sees them before
    // the first save. Mirrors dcr.api.lending._populate_deal_reference which
    // runs again on validate as the authoritative source of truth.
    if (!frm.doc.loan_application) return;

    frappe.call({
        method: 'dcr.api.lending.get_loan_deal_reference',
        args: {
            loan_application: frm.doc.loan_application,
            applicant: frm.doc.applicant
        },
        callback: function(r) {
            if (!r.message) return;
            Object.keys(r.message).forEach(function(field) {
                if (r.message[field] && !frm.doc[field]) {
                    frm.set_value(field, r.message[field]);
                }
            });
            calculate_loan_preview(frm);
        }
    });
}


function calculate_loan_preview(frm) {
    // Calculated totals are read-only on submitted Loans. The validate hook
    // has already persisted them, so do not dirty a submitted form on refresh.
    if (frm.doc.docstatus && frm.doc.docstatus !== 0) return;

    dcr.update_dated_loan_preview(frm, set_loan_calculated_value);

}


function set_loan_calculated_value(frm, fieldname, value) {
    if (!frm.fields_dict[fieldname]) return;
    var current = frm.doc[fieldname];
    if (value === null || value === undefined) {
        // Empty numeric fields reload as zero in Frappe. Writing null again
        // would dirty the draft after every save, hiding its Submit action.
        var type = (frm.fields_dict[fieldname].df || {}).fieldtype;
        if (['Currency', 'Float', 'Percent', 'Int'].includes(type) && Number(current) === 0) return;
        if (current !== null && current !== undefined && current !== '') {
            frm.set_value(fieldname, null);
        }
        return;
    }
    if (Math.abs(parseFloat(current || 0) - value) > 0.000001) {
        frm.set_value(fieldname, value);
    }
}


function show_autopay_indicator(frm) {
    var loan_name = frm.doc.name;
    // Clear any existing headline first to prevent duplicates
    frm.dashboard.clear_headline();

    frappe.call({
        method: 'dcr.api.achq_integration.get_loan_account_info',
        args: { loan: loan_name },
        callback: function(r) {
            if (frm.doc.name !== loan_name) return;
            frm.dashboard.clear_headline();
            if (r.message && r.message.has_account) {
                var info = r.message;
                // Account resolution proves linkage, not debit activation. Only
                // display a four-digit mask; never render a missing or full number.
                var mask = String(info.account_last4 || '').trim();
                var bank_name = frappe.utils.escape_html(info.bank_name || __('Bank'));
                var headline = /^\d{4}$/.test(mask)
                    ? __('Bank account: {0} ending in {1}', [bank_name, mask])
                    : __('Bank account: {0} (account number unavailable)', [bank_name]);
                frm.dashboard.set_headline(headline, 'blue');
            } else {
                frm.dashboard.set_headline(
                    '<span style="display:flex;justify-content:space-between;align-items:center;width:100%">' +
                    '<span>' + __('Bank account: Not linked') + '</span>' +
                    '<button class="btn btn-xs btn-primary resend-autopay-email" style="font-weight:600;">Resend Setup Email</button>' +
                    '</span>',
                    'orange'
                );
                // Bind after headline renders
                frm.$wrapper.find('.resend-autopay-email').on('click', function() {
                    $(this).prop('disabled', true).text('Sending...');
                    frappe.call({
                        method: 'dcr.api.dcr_email.send_autopay_update_email',
                        args: { customer: frm.doc.applicant },
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: __('Auto-pay setup email sent to dealer'),
                                    indicator: 'green'
                                });
                            }
                        },
                        always: function() {
                            frm.$wrapper.find('.resend-autopay-email').prop('disabled', false).text('Resend Setup Email');
                        }
                    });
                });
            }
        }
    });
}


function send_disbursement_notice(frm) {
    frappe.db.get_value('Customer', frm.doc.applicant, 'email_id', function(r) {
        if (!r || !r.email_id) {
            frappe.msgprint(__('Customer {0} does not have an email address.', [frm.doc.applicant]));
            return;
        }

        frappe.confirm(
            __('Send Disbursement Notice to {0} ({1})?', [frm.doc.applicant, r.email_id]),
            function() {
                frappe.call({
                    method: 'dcr.api.dcr_email.send_loan_disbursed',
                    args: {
                        customer_name: frm.doc.applicant_name || frm.doc.applicant,
                        factory_name: frm.doc.factory || '',
                        loan: frm.doc.name,
                        home_build_request: frm.doc.home_build_request || '',
                        amount: frm.doc.loan_amount,
                        to_email: r.email_id,
                        reference_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Sending disbursement notice...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Disbursement Notice sent'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            }
        );
    });
}


function send_payoff(frm, payoff_type) {
    frappe.confirm(
        __('Send {0} Payoff Letter to {1}?', [payoff_type, frm.doc.applicant]),
        function() {
            frappe.call({
                method: 'dcr.api.docusign.send_payoff_letter',
                args: { loan: frm.doc.name, payoff_type: payoff_type },
                freeze: true,
                freeze_message: __('Sending payoff letter...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('{0} Payoff Letter sent', [payoff_type]),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    );
}
