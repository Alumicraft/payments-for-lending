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
    return dcr.preview_signature(frm, 'MIFA', 'dcr.api.docusign.send_mifa_for_signature', 'mifa_name');
}
