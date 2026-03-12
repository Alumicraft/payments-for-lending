/**
 * Home Build Request Form Customization
 *
 * Auto-populates the Document Checklist when home_type, financing_type,
 * or property_type changes.
 */

frappe.ui.form.on('Home Build Request', {
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
