/**
 * Home Build Request Form Customization
 *
 * Features:
 * - Auto-populates Document Checklist on field change
 * - Create → Sales Order button (after submission)
 */

frappe.ui.form.on('Home Build Request', {
    refresh: function(frm) {
        // Create → Sales Order (submitted HBRs without a linked SO)
        if (frm.doc.docstatus === 1 && !frm.doc.sales_order) {
            frm.add_custom_button(__('Sales Order'), function() {
                frappe.new_doc('Sales Order', {
                    home_build_request: frm.doc.name,
                    customer: frm.doc.customer,
                    home_type: frm.doc.home_type,
                    financing_type: frm.doc.financing_type,
                    property_type: frm.doc.property_type
                });
            }, __('Create'));
        }
    },
    home_type: function(frm) { populate_checklist(frm); },
    financing_type: function(frm) { populate_checklist(frm); },
    property_type: function(frm) { populate_checklist(frm); },
});


function populate_checklist(frm) {
    if (!frm.doc.home_type || !frm.doc.financing_type || !frm.doc.property_type) {
        return;
    }

    frappe.call({
        method: 'dcr.dcr.doctype.home_build_request.home_build_request.get_required_docs',
        args: {
            home_type: frm.doc.home_type,
            financing_type: frm.doc.financing_type,
            property_type: frm.doc.property_type
        },
        callback: function(r) {
            if (!r.message || r.message.length === 0) {
                return;
            }

            // Clear existing checklist rows
            frm.clear_table('doc_checklist');

            // Add required docs
            for (const doc_type of r.message) {
                let row = frm.add_child('doc_checklist');
                row.document_type = doc_type;
                row.status = 'Pending';
            }

            frm.refresh_field('doc_checklist');
            frappe.show_alert({
                message: __('Document checklist updated — {0} documents required', [r.message.length]),
                indicator: 'blue'
            });
        }
    });
}
