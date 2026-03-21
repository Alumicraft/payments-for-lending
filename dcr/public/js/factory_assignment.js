/**
 * Factory Assignment Form Customization
 *
 * Buttons:
 * - "Mark as Approved" (top-level) — after LOA received from factory
 * - "Mark as Rejected" (top-level) — if factory declines
 */

frappe.ui.form.on('Factory Assignment', {
    refresh: function(frm) {
        if (frm.doc.docstatus !== 1) return;

        // Status progression buttons — only when application is submitted and pending
        if (frm.doc.retailer_application_status === 'Submitted') {
            frm.add_custom_button(__('Mark as Approved'), function() {
                frappe.confirm(
                    __('Mark this factory assignment as Approved? This indicates the LOA has been received.'),
                    function() {
                        frappe.call({
                            method: 'frappe.client.set_value',
                            args: {
                                doctype: 'Factory Assignment',
                                name: frm.doc.name,
                                fieldname: 'retailer_application_status',
                                value: 'Approved'
                            },
                            callback: function() {
                                frappe.show_alert({
                                    message: __('Factory Assignment approved'),
                                    indicator: 'green'
                                });
                                frm.reload_doc();
                            }
                        });
                    }
                );
            });
            frm.change_custom_button_type(__('Mark as Approved'), null, 'primary');

            frm.add_custom_button(__('Mark as Rejected'), function() {
                frappe.confirm(
                    __('Mark this factory assignment as Rejected?'),
                    function() {
                        frappe.call({
                            method: 'frappe.client.set_value',
                            args: {
                                doctype: 'Factory Assignment',
                                name: frm.doc.name,
                                fieldname: 'retailer_application_status',
                                value: 'Rejected'
                            },
                            callback: function() {
                                frappe.show_alert({
                                    message: __('Factory Assignment rejected'),
                                    indicator: 'red'
                                });
                                frm.reload_doc();
                            }
                        });
                    }
                );
            });
        }
    }
});
