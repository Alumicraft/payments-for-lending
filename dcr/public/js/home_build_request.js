/**
 * Home Build Request Form Customization
 *
 * Features:
 * - Auto-populates Document Checklist on field change
 * - Create → Sales Order button (after submission)
 */

frappe.ui.form.on('Home Build Request', {
    refresh: function(frm) {
        // Create → Loan Application (Floored only, no existing LA)
        if (frm.doc.docstatus === 1 && frm.doc.financing_type === 'Floored' && !frm.doc.loan_application) {
            frm.add_custom_button(__('Loan Application'), function() {
                frappe.call({
                    method: 'dcr.dcr.doctype.home_build_request.home_build_request.create_loan_application_from_hbr',
                    args: { hbr_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Creating Loan Application...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Create'));
            frm.change_custom_button_type(__('Loan Application'), __('Create'), 'primary');
        }

        // Create → Supplier Quotation (submitted, no factory_quote linked, factory set)
        if (frm.doc.docstatus === 1 && !frm.doc.factory_quote && frm.doc.factory) {
            frm.add_custom_button(__('Supplier Quotation'), function() {
                frappe.new_doc('Supplier Quotation', {
                    supplier: frm.doc.factory,
                    home_build_request: frm.doc.name
                });
            }, __('Create'));
            frm.change_custom_button_type(__('Supplier Quotation'), __('Create'), 'primary');
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
