// dcr/public/js/mifa.js

frappe.ui.form.on('MIFA', {
    refresh: function(frm) {
        if (frm.is_new() || !frm.doc.customer) return;

        // Don't show send button if already signed
        if (frm.doc.signed_mifa) return;

        frm.add_custom_button(__('Send for Signature'), function() {
            send_mifa(frm);
        }, __('Actions'));
    }
});

function send_mifa(frm) {
    // Validate customer has email
    frappe.db.get_value('Customer', frm.doc.customer, 'email_id', function(r) {
        if (!r || !r.email_id) {
            frappe.msgprint(__('Customer {0} does not have an email address. Please update the Customer record first.', [frm.doc.customer]));
            return;
        }

        frappe.confirm(
            __('Send MIFA to {0} ({1}) for signature via DocuSign?', [frm.doc.customer, r.email_id]),
            function() {
                frappe.call({
                    method: 'dcr.api.docusign.send_mifa_for_signature',
                    args: { mifa_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Sending MIFA for signature...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('MIFA sent for signature via DocuSign'),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    });
}
