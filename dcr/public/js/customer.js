/**
 * Customer Form Customization for DCR Dealers
 *
 * Buttons:
 * - Email → "Dealer Agreement" — Dealer Agreement via DocuSign
 * - Create → MIFA — after dealer agreement is signed
 * - Create → Factory Assignment — if none exists
 * - Actions → "Send Bank Update Email" — send Plaid setup link
 *
 * Bank account management uses standard Bank Account "+" on Customer form.
 */

frappe.ui.form.on('Customer', {
    refresh: function(frm) {
        if (frm.doc.customer_group !== 'Dealer' || frm.is_new()) {
            return;
        }

        // Signing status indicator
        if (frm.doc.dealer_agreement_status === 'Signed') {
            frm.page.set_indicator(__('Agreement Signed'), 'green');
        } else if (frm.doc.dealer_agreement_status === 'Sent') {
            frm.page.set_indicator(__('Awaiting Signature'), 'orange');
        }

        // Email: Dealer Agreement (for signature)
        if (frm.doc.dealer_agreement_status !== 'Signed') {
            frm.add_custom_button(__('Dealer Agreement'), function() {
                send_dealer_agreement(frm);
            }, __('Email'));
        }

        // Create → MIFA (after dealer agreement is signed)
        if (frm.doc.dealer_agreement_status === 'Signed') {
            frappe.db.count('MIFA', { customer: frm.doc.name }).then(function(count) {
                if (count === 0) {
                    frm.add_custom_button(__('MIFA'), function() {
                        frappe.new_doc('MIFA', {
                            customer: frm.doc.name
                        });
                    }, __('Create'));
                    frm.change_custom_button_type(__('MIFA'), __('Create'), 'primary');
                }
            });
        }

        // Create → Factory Assignment
        frm.add_custom_button(__('Factory Assignment'), function() {
            frappe.new_doc('Factory Assignment', {
                customer: frm.doc.name
            });
        }, __('Create'));

        // Actions: Send Bank Update Email
        frappe.call({
            method: 'dcr.dcr.doctype.ach_settings.ach_settings.is_ach_enabled',
            callback: function(r) {
                if (r.message) {
                    frm.add_custom_button(__('Send Bank Update Email'), function() {
                        send_bank_update_email(frm);
                    }, __('Actions'));
                }
            }
        });
    }
});


function send_dealer_agreement(frm) {
    if (!frm.doc.email_id) {
        frappe.msgprint(__('Please set an email address for this customer before sending the agreement.'));
        return;
    }

    frappe.confirm(
        __('Send Dealer Agreement to {0}?', [frm.doc.email_id]),
        function() {
            frappe.call({
                method: 'dcr.api.docusign.send_dealer_agreement',
                args: { customer: frm.doc.name },
                freeze: true,
                freeze_message: __('Sending agreement...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Dealer Agreement sent for signature'),
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}


function send_bank_update_email(frm) {
    if (!frm.doc.email_id) {
        frappe.msgprint(__('Please set an email address for this customer first.'));
        return;
    }

    frappe.confirm(
        __('Send bank account update email to {0} ({1})?', [frm.doc.customer_name, frm.doc.email_id]),
        function() {
            frappe.call({
                method: 'dcr.api.dcr_email.send_autopay_update_email',
                args: { customer: frm.doc.name },
                freeze: true,
                freeze_message: __('Sending email...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Bank update email sent to {0}', [frm.doc.email_id]),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    );
}
