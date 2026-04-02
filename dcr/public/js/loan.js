/**
 * Loan Form Customization
 *
 * Buttons:
 * - Email → "Disbursement Notice" — notify dealer of disbursement
 * - Email → "FL Payoff Letter" / "COD Payoff Letter" — payoff letters
 *
 * Indicators:
 * - Auto-Pay status (green if bank account linked, red if not)
 *
 * Auto-Pay setup email is sent automatically on save when no bank account
 * is linked (server-side, with 24-hour dedup).
 */

frappe.ui.form.on('Loan', {
    refresh: function(frm) {
        if (frm.is_new()) {
            return;
        }

        // Auto-Pay status indicator (show on saved and submitted loans)
        show_autopay_indicator(frm);

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
    }
});


function show_autopay_indicator(frm) {
    // Clear any existing headline first to prevent duplicates
    frm.dashboard.clear_headline();

    frappe.call({
        method: 'dcr.api.achq_integration.get_loan_account_info',
        args: { loan: frm.doc.name },
        callback: function(r) {
            frm.dashboard.clear_headline();
            if (r.message && r.message.has_account) {
                var info = r.message;
                frm.dashboard.set_headline(
                    __('Auto-Pay: {0} ending in {1}', [info.bank_name || 'Bank', info.account_last4]),
                    'green'
                );
            } else {
                frm.dashboard.set_headline(
                    '<span style="display:flex;justify-content:space-between;align-items:center;width:100%">' +
                    '<span>' + __('Auto-Pay: No bank account linked') + '</span>' +
                    '<button class="btn btn-xs btn-default resend-autopay-email">Resend Setup Email</button>' +
                    '</span>',
                    'red'
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
                        home_build_request: frm.doc.home_serial_no || '',
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
