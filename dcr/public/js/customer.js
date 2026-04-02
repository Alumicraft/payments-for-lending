/**
 * Customer Form Customization for DCR Dealers
 *
 * Buttons:
 * - Email → "Dealer Agreement" — Dealer Agreement via DocuSign
 * - Create → MIFA — after dealer agreement is signed
 * - Create → Factory Assignment — if none exists
 *
 * Bank account management uses standard Bank Account "+" on Customer form.
 * Auto-Pay setup email is sent from the Loan form.
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
