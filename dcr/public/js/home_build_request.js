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

var _mapbox_token = null;
var _mapbox_session = null;
var _address_fields = ['city', 'state', 'zip', 'latitude', 'longitude'];

function setup_address_autofill(frm) {
    var $input = frm.fields_dict.delivery_address && frm.fields_dict.delivery_address.$input;
    if (!$input || _mapbox_bound[frm.doc.name]) return;
    _mapbox_bound[frm.doc.name] = true;

    // If address already has auto-filled data, lock the dependent fields
    if (frm.doc.latitude && frm.doc.longitude) {
        set_address_fields_read_only(frm, true);
    }

    var _debounce = null;

    $input.on('input', function() {
        var query = $input.val();

        // If field is cleared, reset all auto-filled fields
        if (!query) {
            clear_address_fields(frm);
            return;
        }

        if (query.length < 3) return;

        clearTimeout(_debounce);
        _debounce = setTimeout(function() {
            get_mapbox_token(function(token) {
                if (!token) return;
                search_mapbox(token, query, function(suggestions) {
                    if (suggestions.length) show_address_dropdown(frm, $input, suggestions, token);
                });
            });
        }, 300);
    });
}

function get_mapbox_token(callback) {
    if (_mapbox_token) { callback(_mapbox_token); return; }
    frappe.call({
        method: 'dcr.api.map.get_map_settings',
        callback: function(r) {
            if (r.message && r.message.access_token) {
                _mapbox_token = r.message.access_token;
                callback(_mapbox_token);
            } else {
                callback(null);
            }
        }
    });
}

function get_session_token() {
    if (!_mapbox_session) {
        // Generate a UUID v4 for Mapbox session tracking
        _mapbox_session = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }
    return _mapbox_session;
}

function search_mapbox(token, query, callback) {
    // Client-side search — avoids server token URL restriction issues
    var url = 'https://api.mapbox.com/search/searchbox/v1/suggest'
        + '?q=' + encodeURIComponent(query)
        + '&access_token=' + token
        + '&session_token=' + get_session_token()
        + '&language=en&country=US&types=address&limit=5';

    fetch(url).then(function(r) { return r.json(); }).then(function(data) {
        callback(data.suggestions || []);
    }).catch(function() { callback([]); });
}

function retrieve_mapbox(token, mapbox_id, callback) {
    var url = 'https://api.mapbox.com/search/searchbox/v1/retrieve/' + mapbox_id
        + '?access_token=' + token
        + '&session_token=' + get_session_token();

    fetch(url).then(function(r) { return r.json(); }).then(function(data) {
        var features = data.features || [];
        if (features.length) {
            var props = features[0].properties || {};
            var coords = (features[0].geometry || {}).coordinates || [0, 0];
            callback({
                full_address: props.full_address || '',
                address: props.address || '',
                city: props.place || '',
                state: props.region_code || props.region || '',
                zip: props.postcode || '',
                latitude: coords[1] || 0,
                longitude: coords[0] || 0
            });
        } else {
            callback(null);
        }
    }).catch(function() { callback(null); });
}

function set_address_fields_read_only(frm, read_only) {
    for (var i = 0; i < _address_fields.length; i++) {
        frm.set_df_property(_address_fields[i], 'read_only', read_only ? 1 : 0);
    }
    // Show/hide clear button on delivery_address
    var $wrapper = frm.fields_dict.delivery_address && frm.fields_dict.delivery_address.$wrapper;
    if (!$wrapper) return;
    $wrapper.find('.address-clear-btn').remove();
    if (read_only && !frm.doc.docstatus) {
        var $btn = $('<span class="address-clear-btn" title="Clear address">&times;</span>').css({
            position: 'absolute',
            right: '8px',
            top: '50%',
            transform: 'translateY(-50%)',
            cursor: 'pointer',
            fontSize: '18px',
            color: '#8d99a6',
            zIndex: 10,
            lineHeight: 1
        }).on('click', function() {
            frm.set_value('delivery_address', '');
            clear_address_fields(frm);
        });
        $wrapper.find('.control-input').css('position', 'relative').append($btn);
    }
}

function clear_address_fields(frm) {
    for (var i = 0; i < _address_fields.length; i++) {
        frm.set_value(_address_fields[i], '');
    }
    set_address_fields_read_only(frm, false);
}

function show_address_dropdown(frm, $input, suggestions, token) {
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
            var label = s.full_address || s.name || '';
            var $li = $('<li></li>')
                .text(label)
                .css({ padding: '8px 12px', cursor: 'pointer', fontSize: '13px' })
                .on('mousedown', function(e) {
                    e.preventDefault();
                    $dropdown.remove();

                    // Retrieve full details for the selected suggestion
                    var mid = s.mapbox_id;
                    if (!mid) return;

                    retrieve_mapbox(token, mid, function(result) {
                        if (!result) return;
                        frm.set_value('delivery_address', result.address || '');
                        frm.set_value('city', result.city || '');
                        frm.set_value('state', result.state || '');
                        frm.set_value('zip', result.zip || '');
                        frm.set_value('latitude', result.latitude || 0);
                        frm.set_value('longitude', result.longitude || 0);
                        set_address_fields_read_only(frm, true);
                    });
                })
                .on('mouseenter', function() { $(this).css('background', '#f5f7fa'); })
                .on('mouseleave', function() { $(this).css('background', '#fff'); });
            $dropdown.append($li);
        })(suggestions[i]);
    }

    $input.parent().css('position', 'relative').append($dropdown);

    $input.one('blur', function() {
        setTimeout(function() { $dropdown.remove(); }, 200);
    });
}
