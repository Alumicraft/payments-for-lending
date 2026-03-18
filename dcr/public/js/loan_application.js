// dcr/public/js/loan_application.js

frappe.ui.form.on('Loan Application', {
    refresh: function(frm) {
        if (frm.is_new()) return;

        // Only show DCR buttons if linked to a Home Build Request
        if (!frm.doc.home_build_request) return;

        // Send Flooring Packet button (DocuSign)
        // Show if no signed packet yet
        if (!frm.doc.signed_packet) {
            frm.add_custom_button(__('Send Flooring Packet'), function() {
                send_flooring_packet(frm);
            }, __('DocuSign'));
        }

        // Send Advance Pre-Approval button
        frm.add_custom_button(__('Send Pre-Approval'), function() {
            send_pre_approval(frm);
        }, __('Actions'));
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
