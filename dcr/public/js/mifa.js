/**
 * MIFA Form Customization
 *
 * Buttons:
 * - "Send for Signature" (top-level) — MIFA via DocuSign (requires submission)
 *
 * Indicators:
 * - Signed (green) — signed MIFA attached
 * - Awaiting Signature (orange) — Signature Request sent
 */

frappe.ui.form.on('MIFA', {
    refresh: function(frm) {
        if (frm.is_new()) return;

        // Signing status indicator (show on any saved MIFA)
        if (frm.doc.signed_mifa) {
            frm.page.set_indicator(__('Signed'), 'green');
        } else {
            frappe.db.get_value('Signature Request',
                {reference_doctype: 'MIFA', reference_name: frm.doc.name, status: 'Sent'},
                'name', function(r) {
                    if (r && r.name) {
                        frm.page.set_indicator(__('Awaiting Signature'), 'orange');
                    }
                });
        }

        // Buttons require submission
        if (frm.doc.docstatus !== 1) return;

        if (!frm.doc.signed_mifa) {
            frm.add_custom_button(__('Send for Signature'), function() {
                send_mifa(frm);
            });
        }
    }
});

function send_mifa(frm) {
    // Validate required fields before sending
    if (!frm.doc.credit_limit || frm.doc.credit_limit <= 0) {
        frappe.msgprint(__('Credit Limit must be set before sending for signature.'));
        return;
    }
    if (!frm.doc.loan_product) {
        frappe.msgprint(__('Loan Product must be set before sending for signature.'));
        return;
    }

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
