/**
 * Home Build Request Form Customization
 *
 * Features:
 * - Auto-populates Document Checklist on field change
 * - Create → Loan Application button (Floored deals, after submission)
 * - Create → Supplier Quotation button (after submission)
 */

frappe.ui.form.on('Home Build Request', {
    refresh: function(frm) {
        // Factory filter
        if (frm.doc.customer) {
            frm.set_query('factory', function() {
                return {
                    query: 'dcr.dcr.doctype.home_build_request.home_build_request.get_assigned_factories',
                    filters: { customer: frm.doc.customer }
                };
            });
        }

        frm.set_query('home_buyer', function() {
            return {
                filters: {
                    'customer_group': 'Home Buyer'
                }
            };
        });

        frm.set_query('escrow_company', function() {
            return {
                filters: {
                    'supplier_group': 'Escrow'
                }
            };
        });

        // Create buttons only on submitted HBR
        if (frm.doc.docstatus !== 1) return;

        // Create → Loan Application (Floored only, if none exists)
        if (frm.doc.financing_type === 'Floored') {
            frappe.db.count('Loan Application', {
                filters: { home_build_request: frm.doc.name, docstatus: ['!=', 2] }
            }).then(function(count) {
                if (count === 0) {
                    frm.add_custom_button(__('Loan Application'), function() {
                        frappe.new_doc('Loan Application', {
                            applicant_type: 'Customer',
                            applicant: frm.doc.customer,
                            home_build_request: frm.doc.name
                        });
                    }, __('Create'));
                }
            });
        }

        // Create → Purchase Invoice (all deals)
        frm.add_custom_button(__('Purchase Invoice'), function() {
            frappe.new_doc('Purchase Invoice', {
                supplier: frm.doc.factory,
                home_build_request: frm.doc.name
            });
        }, __('Create'));
    },
    customer: function(frm) {
        if (frm.doc.customer) {
            frm.set_query('factory', function() {
                return {
                    query: 'dcr.dcr.doctype.home_build_request.home_build_request.get_assigned_factories',
                    filters: { customer: frm.doc.customer }
                };
            });
        }
    },
    escrow_company: function(frm) {
        if (!frm.doc.escrow_company) {
            frm.set_value('escrow_contact', '');
            frm.set_value('escrow_phone', '');
            return;
        }
        // Find Contact via Dynamic Link child table
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Dynamic Link',
                filters: {
                    parenttype: 'Contact',
                    link_doctype: 'Supplier',
                    link_name: frm.doc.escrow_company
                },
                fields: ['parent'],
                limit_page_length: 1
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    frappe.db.get_value('Contact', r.message[0].parent,
                        ['first_name', 'last_name', 'mobile_no', 'phone'],
                        function(contact) {
                            if (!contact) return;
                            let name = contact.first_name || '';
                            if (contact.last_name) name += ' ' + contact.last_name;
                            frm.set_value('escrow_contact', name.trim());
                            frm.set_value('escrow_phone', contact.mobile_no || contact.phone || '');
                        }
                    );
                } else {
                    frm.set_value('escrow_contact', '');
                    frm.set_value('escrow_phone', '');
                }
            }
        });
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
            }

            frm.refresh_field('doc_checklist');
            frappe.show_alert({
                message: __('Document checklist updated — {0} documents required', [r.message.length]),
                indicator: 'blue'
            });
        }
    });
}
