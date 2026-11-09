/**
 * Customer Form Customization for DCR Dealers
 *
 * Buttons:
 * - Email → "Dealer Agreement" — Dealer Agreement via DocuSign
 * - Create → MIFA — after dealer agreement is signed
 * - Create → Factory Assignment — if none exists
 *
 * Create → Verify bank account — manual verification without enabling debits.
 * Auto-Pay setup email is sent from the Loan form.
 */

frappe.ui.form.on('Customer', {
    refresh: function(frm) {
        if (frm.doc.customer_group !== 'Dealer' || frm.is_new()) {
            return;
        }

        patch_dealer_document_uploads(frm);

        if (frappe.model.can_create('Bank Account') && frappe.model.can_write('Customer')) {
            frm.add_custom_button(__('Verify bank account'), function() {
                verify_dealer_bank_account(frm);
            }, __('Create'));
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


function verify_dealer_bank_account(frm) {
    var dialog = new frappe.ui.Dialog({
        title: __('Verify bank account'),
        fields: [
            { fieldname: 'routing_number', label: __('Routing number'), fieldtype: 'Data', reqd: 1 },
            { fieldname: 'account_number', label: __('Account number'), fieldtype: 'Password', reqd: 1 },
            { fieldname: 'account_type', label: __('Account type'), fieldtype: 'Select', options: ['Checking', 'Savings'], default: 'Checking', reqd: 1 },
            { fieldname: 'check_type', label: __('Account holder'), fieldtype: 'Select', options: ['Business', 'Personal'], default: 'Business', reqd: 1 },
            { fieldname: 'is_default', label: __('Use as default bank account'), fieldtype: 'Check', default: 0,
                description: __('This account stays paused until dealer debit authorization is recorded. Verifying it does not enable automatic payments.') }
        ],
        primary_action_label: __('Verify'),
        onhide: function() {
            dialog.set_value('account_number', '');
            dialog.set_value('routing_number', '');
        },
        primary_action: async function(values) {
            dialog.get_primary_btn().prop('disabled', true);
            try {
                var result = await frappe.call({
                    method: 'dcr.api.achq_integration.setup_bank_account',
                    args: Object.assign({ customer: frm.doc.name }, values)
                });
                if (result.message && result.message.success) {
                    dialog.hide();
                    frappe.show_alert({ message: __('Bank account verified and connected'), indicator: 'green' });
                    await frm.reload_doc();
                }
            } finally {
                dialog.get_primary_btn().prop('disabled', false);
            }
        }
    });
    dialog.show();
    dialog.fields_dict.account_number.$input.attr('autocomplete', 'off');
}


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
    return dcr.preview_signature(frm, 'Dealer Agreement', 'dcr.api.docusign.send_dealer_agreement', 'customer');
}
