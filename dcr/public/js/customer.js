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

        patch_dealer_document_uploads(frm);

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


var DEALER_DOCUMENT_FIELDS = [
    'dealer_license_copy',
    'sellers_permit_copy',
    'w9_copy',
    'retailer_application_copy'
];


function patch_dealer_document_uploads(frm) {
    DEALER_DOCUMENT_FIELDS.forEach(function(fieldname) {
        var control = frm.fields_dict[fieldname];
        if (!control || control.__dcr_serial_upload) return;

        control.__dcr_serial_upload = true;
        control.on_upload_complete = function(attachment) {
            var attach_control = this;
            var previous_save = frm.__dcr_dealer_document_save_queue || Promise.resolve();

            // Frappe's upload endpoint adds an Attachment comment before the
            // Attach control saves the field. That comment advances the parent
            // Customer's modified timestamp, so saving the already-open form
            // immediately afterwards can fail its optimistic-lock check. Save
            // only this field through a fresh server-side Customer document,
            // and queue calls so consecutive uploads cannot race each other.
            var queued_save = previous_save
                .catch(function() {
                    // A failed upload must not permanently block later files.
                })
                .then(async function() {
                    var was_dirty = frm.is_dirty && frm.is_dirty();
                    await attach_control.parse_validate_and_set_in_model(attachment.file_url);
                    frm.attachments.update_attachment(attachment);

                    var response = await frappe.call({
                        method: 'dcr.api.dealer_documents.set_dealer_document',
                        args: {
                            customer: frm.doc.name,
                            fieldname: fieldname,
                            file_url: attachment.file_url
                        }
                    });

                    if (response.message && response.message.modified) {
                        frm.doc.modified = response.message.modified;
                    }
                    if (!was_dirty) {
                        frm.doc.__unsaved = 0;
                        removeEventListener('beforeunload', frm.beforeUnloadListener, { capture: true });
                        frm.refresh_header();
                    }
                    attach_control.refresh();
                });

            frm.__dcr_dealer_document_save_queue = queued_save;
            return queued_save;
        };
    });
}


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
