/**
 * Home Build Request Form Customization
 *
 * Features:
 * - Auto-populates Document Checklist on field change
 * - Create → Loan Application button (Floored deals, after submission)
 * - Create → Purchase Order / Purchase Invoice (all deals, after submission)
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

        // Mapbox address autofill (only on draft forms)
        if (!frm.doc.docstatus) {
            setup_address_autofill(frm);
        }

        // Hide Lending connections (Loan Application / Loan / Loan
        // Disbursement) on Cash deals — those only exist for Floored.
        update_connections_visibility(frm);
        update_stage_field_visibility(frm);
        bind_loan_application_connection_create(frm);

        // Create buttons only on submitted HBR
        if (frm.doc.docstatus !== 1) return;

        // Create → Loan Application (Floored deals only, if none exists)
        if (frm.doc.financing_type === 'Floored') {
            frappe.db.count('Loan Application', {
                filters: { home_build_request: frm.doc.name, docstatus: ['!=', 2] }
            }).then(function(count) {
                if (count === 0) {
                    frm.add_custom_button(__('Loan Application'), function() {
                        create_loan_application_from_hbr(frm);
                    }, __('Create'));
                }
            });
        }

        // Create → Purchase Order (all deals)
        frm.add_custom_button(__('Purchase Order'), function() {
            frappe.new_doc('Purchase Order', {
                supplier: frm.doc.factory,
                custom_home_build_request: frm.doc.name
            });
        }, __('Create'));

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
    financing_type: function(frm) {
        populate_checklist(frm);
        update_connections_visibility(frm);
        update_stage_field_visibility(frm);
    },
    property_type: function(frm) { populate_checklist(frm); },
});


function create_loan_application_from_hbr(frm) {
    var defaults = {
        applicant_type: 'Customer',
        applicant: frm.doc.customer,
        home_build_request: frm.doc.name
    };

    frappe.call({
        method: 'dcr.api.lending.get_loan_application_defaults',
        args: { home_build_request: frm.doc.name },
        callback: function(r) {
            frappe.new_doc('Loan Application', Object.assign(defaults, r.message || {}));
        },
        error: function() {
            frappe.new_doc('Loan Application', defaults);
        }
    });
}


function bind_loan_application_connection_create(frm) {
    if (frm.doc.docstatus !== 1 || frm.doc.financing_type !== 'Floored') return;

    function is_loan_application_connection_click(target) {
        if (!target || !target.closest) return false;

        var button = target.closest('button, .btn-new');
        if (!button) return false;

        var card = button.closest(
            '.document-link, .document-link-badge, .link-item, ' +
            '.col-md-4, .col-sm-6, .col-xs-12'
        );
        if (!card) return false;

        var doctype = card.getAttribute('data-doctype') || $(card).data('doctype');
        if (doctype) return doctype === 'Loan Application';

        return $(card).text().trim().indexOf('Loan Application') !== -1;
    }

    function intercept(e) {
        if (!is_loan_application_connection_click(e.target)) return;

        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        create_loan_application_from_hbr(frm);
        return false;
    }

    function connection_wrappers() {
        var wrappers = $();
        if (frm.dashboard && frm.dashboard.wrapper) {
            wrappers = wrappers.add(frm.dashboard.wrapper);
        }
        if (frm.wrapper) {
            wrappers = wrappers.add($(frm.wrapper).find('.form-documents'));
        }
        wrappers = wrappers.add($('.form-documents'));
        return wrappers;
    }

    function bind() {
        var $wrapper = connection_wrappers();
        $wrapper.each(function() {
            if (this.__dcr_loan_application_connection_intercept) return;
            this.__dcr_loan_application_connection_intercept = true;
            this.addEventListener('click', intercept, true);
        });

        var $cards = $wrapper.find(
            '.document-link[data-doctype="Loan Application"], ' +
            '.document-link:contains("Loan Application"), ' +
            '.document-link-badge:contains("Loan Application"), ' +
            '.link-item:contains("Loan Application")'
        );
        if (!$cards.length) return false;

        $cards.each(function() {
            var $card = $(this);
            var $buttons = $card.find('button, .btn-new');
            if (!$buttons.length) return;

            $buttons.off('click.dcrLoanApplicationFromHbr');
            $buttons.on('click.dcrLoanApplicationFromHbr', function(e) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                create_loan_application_from_hbr(frm);
                return false;
            });
        });
        return true;
    }

    var attempts = 0;
    var iv = setInterval(function() {
        attempts += 1;
        bind();
        if (attempts > 30) clearInterval(iv);
    }, 300);
    bind();

    var wrapper = connection_wrappers().get(0);
    if (wrapper && window.MutationObserver) {
        if (frm._dcr_loan_application_connection_observer) {
            frm._dcr_loan_application_connection_observer.disconnect();
        }
        frm._dcr_loan_application_connection_observer = new MutationObserver(function() {
            bind();
        });
        frm._dcr_loan_application_connection_observer.observe(wrapper, { childList: true, subtree: true });
    }
}


function update_connections_visibility(frm) {
    // Frappe renders the connections panel asynchronously — wait a beat,
    // then retry a few times until the cards are in the DOM.
    var lending_doctypes = ['Loan Application', 'Loan', 'Loan Disbursement'];
    var hide_lending = frm.doc.financing_type === 'Cash';

    function connection_wrappers() {
        var wrappers = $();
        if (frm.dashboard && frm.dashboard.wrapper) {
            wrappers = wrappers.add(frm.dashboard.wrapper);
        }
        if (frm.wrapper) {
            wrappers = wrappers.add($(frm.wrapper).find('.form-documents'));
        }
        wrappers = wrappers.add($('.form-documents'));
        return wrappers;
    }

    function apply() {
        var $wrapper = connection_wrappers();
        if (!$wrapper.length) return false;
        var any = false;
        lending_doctypes.forEach(function(dt) {
            var $cards = $wrapper.find('.document-link[data-doctype="' + dt + '"]');
            if ($cards.length) {
                $cards.each(function() {
                    var $card = $(this);
                    var $column = $card.closest('.col-md-4, .col-sm-6, .col-xs-12');
                    ($column.length ? $column : $card).toggle(!hide_lending);
                });
                any = true;
            }
        });
        $wrapper.find('.form-link-title').each(function() {
            var $title = $(this);
            if ($title.text().trim() !== 'Lending') return;
            var $section = $title.closest('.col-md-4, .col-sm-6, .col-xs-12');
            if (!$section.length) $section = $title.parent();
            $section.toggle(!hide_lending);
        });
        return any;
    }

    var attempts = 0;
    var iv = setInterval(function() {
        attempts += 1;
        apply();
        if (attempts > 30) clearInterval(iv);
    }, 300);

    var wrapper = connection_wrappers().get(0);
    if (wrapper && window.MutationObserver) {
        if (frm._dcr_connections_observer) {
            frm._dcr_connections_observer.disconnect();
        }
        frm._dcr_connections_observer = new MutationObserver(function() {
            apply();
        });
        frm._dcr_connections_observer.observe(wrapper, { childList: true, subtree: true });
    }
}


function update_stage_field_visibility(frm) {
    var show_stage = frm.doc.financing_type === 'Floored';

    if (!frm.fields_dict.custom_loan_stage) return;

    // The Custom Field's depends_on is the authoritative rule. This one
    // lightweight wrapper update handles an already-rendered form immediately
    // after a financing-type change without mutating DocField metadata (which
    // was the source of the Floored hide/show flicker).
    frm.toggle_display('custom_loan_stage', show_stage);
}


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
            var required = r.message || [];
            if (required.length === 0) {
                return;
            }

            // Preserve uploads and waivers for requirements that still apply.
            var existing = {};
            (frm.doc.doc_checklist || []).forEach(function(row) {
                if (row.document_type) existing[row.document_type] = row;
            });
            frm.clear_table('doc_checklist');

            for (const doc_type of required) {
                let previous = existing[doc_type] || {};
                let row = frm.add_child('doc_checklist');
                row.document_type = doc_type;
                row.attachment = previous.attachment || '';
                row.waived = previous.waived || 0;
            }

            frm.refresh_field('doc_checklist');
            frappe.show_alert({
                message: __('Document checklist updated — {0} documents required', [required.length]),
                indicator: 'blue'
            });
        }
    });
}

var _address_fields = ['city', 'state', 'zip', 'latitude', 'longitude'];

function setup_address_autofill(frm) {
    var field = frm.fields_dict.delivery_address;
    if (!field) return;
    var $input = field.$input;
    if (!$input || !$input.length) {
        // Field not rendered yet — retry once Frappe finishes painting.
        setTimeout(function() { setup_address_autofill(frm); }, 200);
        return;
    }

    if (frm.doc.latitude && frm.doc.longitude) {
        set_address_fields_read_only(frm, true);
    }

    var _debounce = null;

    // Re-bind cleanly each refresh: form re-renders replace the <input> node,
    // and previously-bound handlers go with it. Namespaced events make the
    // off/on pair idempotent if the same node is re-used.
    $input.off('input.dcrMapbox').on('input.dcrMapbox', function() {
        var query = $input.val();

        if (!query) {
            clear_address_fields(frm);
            return;
        }

        if (query.length < 3) return;

        clearTimeout(_debounce);
        _debounce = setTimeout(function() {
            var request_query = query;
            frm._dcr_address_query = request_query;
            frappe.call({
                method: 'dcr.api.map.search_address',
                args: { query: request_query },
                callback: function(r) {
                    if (frm._dcr_address_query !== request_query) return;
                    var suggestions = r.message || [];
                    if (suggestions.length) {
                        show_address_dropdown(frm, $input, suggestions);
                    } else {
                        // Mapbox tokens can be URL-restricted. The same token
                        // powers the browser map successfully but Mapbox
                        // rejects the server-side request, so retry from the
                        // authenticated browser before reporting no matches.
                        search_address_in_browser(frm, request_query, function(browser_suggestions) {
                            if (frm._dcr_address_query !== request_query) return;
                            if (browser_suggestions.length) {
                                show_address_dropdown(frm, $input, browser_suggestions);
                            } else {
                                $input.parent().find('.mapbox-dropdown').remove();
                            }
                        });
                    }
                }
            });
        }, 300);
    });
}

function search_address_in_browser(frm, query, callback) {
    function search(token) {
        if (!token || !window.fetch || !window.URLSearchParams) {
            callback([]);
            return;
        }

        var params = new URLSearchParams({
            q: query,
            access_token: token,
            language: 'en',
            country: 'US',
            types: 'address',
            limit: '5',
            autocomplete: 'true'
        });
        fetch('https://api.mapbox.com/search/geocode/v6/forward?' + params.toString())
            .then(function(response) {
                if (!response.ok) return { features: [] };
                return response.json();
            })
            .then(function(data) {
                callback((data.features || []).map(parse_mapbox_address_feature));
            })
            .catch(function() {
                callback([]);
            });
    }

    if (frm._dcr_mapbox_token) {
        search(frm._dcr_mapbox_token);
        return;
    }

    frappe.call({
        method: 'dcr.api.map.get_map_settings',
        callback: function(r) {
            frm._dcr_mapbox_token = (r.message && r.message.access_token) || '';
            search(frm._dcr_mapbox_token);
        },
        error: function() {
            callback([]);
        }
    });
}

function parse_mapbox_address_feature(feature) {
    var props = feature.properties || {};
    var context = props.context || {};
    var region = context.region || {};
    var place = context.place || context.locality || {};
    var postcode = context.postcode || {};
    var coords = (feature.geometry && feature.geometry.coordinates) || [0, 0];
    var region_code = props.region_code || region.region_code || region.short_code || '';
    if (region_code.indexOf('-') !== -1) {
        region_code = region_code.split('-').pop();
    }

    return {
        full_address: props.full_address || '',
        address: props.address || props.name_preferred || props.name || '',
        city: props.place || place.name || '',
        state: region_code || props.region || region.name || '',
        zip: props.postcode || postcode.name || '',
        latitude: coords.length > 1 ? coords[1] : 0,
        longitude: coords.length ? coords[0] : 0
    };
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

function show_address_dropdown(frm, $input, suggestions) {
    $input.parent().find('.mapbox-dropdown').remove();

    var $dropdown = $('<ul class="mapbox-dropdown"></ul>').css({
        position: 'absolute',
        zIndex: 100,
        background: 'var(--fg-color)',
        color: 'var(--text-color)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--border-radius)',
        maxHeight: '200px',
        overflowY: 'auto',
        width: '100%',
        listStyle: 'none',
        padding: 0,
        margin: '4px 0 0 0',
        boxShadow: 'var(--shadow-sm)'
    });

    for (var i = 0; i < suggestions.length; i++) {
        (function(s) {
            var $li = $('<li></li>')
                .text(s.full_address)
                .css({ padding: '8px 12px', cursor: 'pointer', fontSize: '13px' })
                .on('mousedown', function(e) {
                    e.preventDefault();
                    $dropdown.remove();
                    frm.set_value('delivery_address', s.address || '');
                    frm.set_value('city', s.city || '');
                    frm.set_value('state', s.state || '');
                    frm.set_value('zip', s.zip || '');
                    frm.set_value('latitude', s.latitude || 0);
                    frm.set_value('longitude', s.longitude || 0);
                    set_address_fields_read_only(frm, true);
                })
                .on('mouseenter', function() { $(this).css('background', 'var(--hover-color)'); })
                .on('mouseleave', function() { $(this).css('background', 'transparent'); });
            $dropdown.append($li);
        })(suggestions[i]);
    }

    $input.parent().css('position', 'relative').append($dropdown);

    $input.one('blur', function() {
        setTimeout(function() { $dropdown.remove(); }, 200);
    });
}
