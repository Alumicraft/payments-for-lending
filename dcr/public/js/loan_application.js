/**
 * Loan Application Form Customization
 *
 * Buttons:
 * - "Send for Signature" (top-level) — Flooring Packet via DocuSign
 * - "Send Pre-Approval" (top-level) — Pre-approval letter email
 * - Create → "Loan" — after flooring packet is signed
 */

frappe.ui.form.on('Loan Application', {
    refresh: function(frm) {
        if (frm.is_new()) return;

        // Only show DCR buttons if linked to a Home Build Request
        if (!frm.doc.home_build_request) return;

        // Top-level: Send for Signature (Flooring Packet)
        if (!frm.doc.signed_packet) {
            frm.add_custom_button(__('Send for Signature'), function() {
                send_flooring_packet(frm);
            });
        }

        // Top-level: Send Pre-Approval
        frm.add_custom_button(__('Send Pre-Approval'), function() {
            send_pre_approval(frm);
        });

        // Create → Loan (after packet is signed and app is submitted)
        if (frm.doc.signed_packet && frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Loan'), function() {
                frappe.model.open_mapped_doc({
                    method: 'lending.loan_management.doctype.loan_application.loan_application.create_loan',
                    frm: frm
                });
            }, __('Create'));
        }
    }
});


function send_flooring_packet(frm) {
    frappe.db.get_value('Customer', frm.doc.applicant, 'email_id', function(r) {
        if (!r || !r.email_id) {
            frappe.msgprint(__('Customer {0} does not have an email address.', [frm.doc.applicant]));
            return;
        }

        frappe.confirm(
            __('Send Flooring Packet (Info Sheet + Exhibit A + ACH Approval) to {0} ({1}) for signature?',
                [frm.doc.applicant, r.email_id]),
            function() {
                frappe.call({
                    method: 'dcr.api.docusign.send_flooring_packet',
                    args: { loan_application: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Generating documents and sending via DocuSign...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Flooring Packet sent for signature'),
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


function send_pre_approval(frm) {
    frappe.db.get_value('Customer', frm.doc.applicant, 'email_id', function(r) {
        if (!r || !r.email_id) {
            frappe.msgprint(__('Customer {0} does not have an email address.', [frm.doc.applicant]));
            return;
        }

        frappe.confirm(
            __('Send Advance Pre-Approval letter to {0} ({1})?', [frm.doc.applicant, r.email_id]),
            function() {
                frappe.call({
                    method: 'dcr.api.docusign.send_pre_approval',
                    args: { loan_application: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Sending pre-approval...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Pre-Approval sent'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            }
        );
    });
}
