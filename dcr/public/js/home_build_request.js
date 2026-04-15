/**
 * Home Build Request Form Customization
 *
 * Features:
 * - Auto-populates Document Checklist on field change
 * - Create → Loan Application button (Floored deals, after submission)
 * - Create → Supplier Quotation button (after submission)
 */

var _mapbox_bound = {};

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

        // Mapbox address autofill (only on draft forms)
        if (!frm.doc.docstatus) {
            setup_address_autofill(frm);
        }

        // Create buttons only on submitted HBR
        if (frm.doc.docstatus !== 1) return;

        // Create → Loan Application (if none exists)
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

function setup_address_autofill(frm) {
    var $input = frm.fields_dict.delivery_address && frm.fields_dict.delivery_address.$input;
    if (!$input || _mapbox_bound[frm.doc.name]) return;
    _mapbox_bound[frm.doc.name] = true;

    var _debounce = null;

    $input.on('input', function() {
        var query = $input.val();
        if (!query || query.length < 3) return;

        clearTimeout(_debounce);
        _debounce = setTimeout(function() {
            frappe.call({
                method: 'dcr.api.map.search_address',
                args: { query: query },
                callback: function(r) {
                    if (!r.message || !r.message.length) return;
                    show_address_dropdown(frm, $input, r.message);
                }
            });
        }, 300);
    });
}

function show_address_dropdown(frm, $input, suggestions) {
    // Remove existing dropdown
    $input.parent().find('.mapbox-dropdown').remove();

    var $dropdown = $('<ul class="mapbox-dropdown"></ul>').css({
        position: 'absolute',
        zIndex: 100,
        background: '#fff',
        border: '1px solid #d1d8dd',
        borderRadius: '4px',
        maxHeight: '200px',
        overflowY: 'auto',
        width: '100%',
        listStyle: 'none',
        padding: 0,
        margin: '4px 0 0 0',
        boxShadow: '0 2px 6px rgba(0,0,0,0.1)'
    });

    for (var i = 0; i < suggestions.length; i++) {
        (function(s) {
            var $li = $('<li></li>')
                .text(s.full_address)
                .css({ padding: '8px 12px', cursor: 'pointer', fontSize: '13px' })
                .on('mousedown', function(e) {
                    e.preventDefault();
                    frm.set_value('delivery_address', s.address || '');
                    frm.set_value('city', s.city || '');
                    frm.set_value('state', s.state || '');
                    frm.set_value('zip', s.zip || '');
                    frm.set_value('latitude', s.latitude || 0);
                    frm.set_value('longitude', s.longitude || 0);
                    $dropdown.remove();
                })
                .on('mouseenter', function() { $(this).css('background', '#f5f7fa'); })
                .on('mouseleave', function() { $(this).css('background', '#fff'); });
            $dropdown.append($li);
        })(suggestions[i]);
    }

    $input.parent().css('position', 'relative').append($dropdown);

    // Close on blur
    $input.one('blur', function() {
        setTimeout(function() { $dropdown.remove(); }, 200);
    });
}
