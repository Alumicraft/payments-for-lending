/**
 * Loan Application Form Customization
 *
 * Buttons:
 * - Email → "Flooring Packet" — Flooring Packet via DocuSign
 * - Email → "Pre-Approval" — Pre-approval letter email
 * - Create → "Loan" — after flooring packet is signed
 */

frappe.ui.form.on('Loan Application', {
    setup: function(frm) {
        // Default applicant_type to Customer (hidden field)
        if (frm.is_new() && !frm.doc.applicant_type) {
            frm.set_value('applicant_type', 'Customer');
        }

        // Only show submitted HBRs in the link dropdown
        frm.set_query('home_build_request', function() {
            return { filters: { docstatus: 1 } };
        });
    },

    onload: function(frm) {
        schedule_hbr_hydration(frm);
    },

    refresh: function(frm) {
        schedule_hbr_hydration(frm);

        // Force-show read-only fields (Frappe v15 hides empty read-only fields on new forms)
        ['rate_of_interest', 'buyer_name', 'available_credit', 'outstanding_loan_balance',
         'custom_current_yn', 'repayment_amount',
         'total_payable_amount', 'total_payable_interest', 'custom_projected_equity',
         'custom_projected_ltv', 'custom_monthly_space_rent', 'custom_quote_amount',
         'applicant_email_address', 'applicant_phone_number'].forEach(function(fn) {
            var field = frm.fields_dict[fn];
            if (field && field.$wrapper) field.$wrapper.show();
        });

        // Submitted applications are authoritative snapshots. Re-running
        // client calculations or credit hydration on refresh marks them
        // "Not Saved" even when the calculated values have not changed.
        // Drafts still need the live preview while the user edits.
        if (frm.doc.docstatus === 0) {
            // Run client-side calcs once with whatever values are in scope
            // (handles fetch_from populating rate_of_interest etc. without a
            // user keystroke firing the field handler).
            refresh_calculations(frm);
        }

        // Fetch loan product + credit info only while the application is
        // editable. The server recalculates these fields again on validate.
        if (frm.doc.docstatus === 0 && frm.doc.applicant) {
            hydrate_applicant_contact(frm);
            if (!frm.doc.loan_product) {
                frappe.db.get_value('Customer', frm.doc.applicant, 'default_loan_product', function(r) {
                    if (r && r.default_loan_product) {
                        frm.set_value('loan_product', r.default_loan_product);
                        refresh_calculations(frm);
                    }
                });
            }
            if (!frm.doc.__credit_fetched) {
                frm.doc.__credit_fetched = true;
                frappe.call({
                    method: 'dcr.api.lending.get_available_credit',
                    args: { customer: frm.doc.applicant },
                    callback: function(r) {
                        if (r.message) {
                            frm.set_value('available_credit', r.message.available);
                            frm.set_value('outstanding_loan_balance', r.message.outstanding);
                            frm.set_value('custom_current_yn', r.message.current_yn);
                        }
                    }
                });
            }
        }

        // Signing status indicator (show on any saved LA with HBR link)
        if (!frm.is_new() && frm.doc.home_build_request) {
            if (frm.doc.signed_packet) {
                frm.page.set_indicator(__('Signed'), 'green');
            } else {
                frappe.db.get_value('Signature Request',
                    {reference_doctype: 'Loan Application', reference_name: frm.doc.name, status: 'Sent'},
                    'name', function(r) {
                        if (r && r.name) {
                            frm.page.set_indicator(__('Awaiting Signature'), 'orange');
                        }
                    });
            }
        }

        // Render the HBR's Document Checklist as a read-only inline
        // table inside the LA's "HBR Documents" custom HTML field
        // (no-op if the field hasn't been added via Customize Form yet).
        render_hbr_documents(frm);

        // Buttons require submission + HBR link
        if (frm.doc.docstatus !== 1) return;
        if (!frm.doc.home_build_request) return;

        // Email: Flooring Packet (for signature)
        if (!frm.doc.signed_packet) {
            frm.add_custom_button(__('Flooring Packet'), function() {
                send_flooring_packet(frm);
            }, __('Email'));
        }

        // Email: Pre-Approval
        frm.add_custom_button(__('Pre-Approval'), function() {
            send_pre_approval(frm);
        }, __('Email'));

        // Create → Loan (available after submit; warns if packet unsigned)
        frm.add_custom_button(__('Loan'), function() {
            if (!frm.doc.signed_packet) {
                frappe.msgprint(__('Flooring Packet has not been signed. Please send and sign the packet before creating a Loan.'));
                return;
            }
            frappe.model.open_mapped_doc({
                method: 'lending.loan_management.doctype.loan_application.loan_application.create_loan',
                frm: frm
            });
        }, __('Create'));
    },

    applicant: function(frm) {
        // Clear fetch cache so credit info re-runs for new applicant
        frm.doc.__credit_fetched = false;
        frm.trigger('refresh');
    },

    home_build_request: function(frm) {
        schedule_hbr_hydration(frm);
    },

    loan_amount: function(frm) {
        calculate_monthly_interest(frm);
        calculate_preapproval_fields(frm);
    },

    rate_of_interest: function(frm) {
        calculate_monthly_interest(frm);
    },

    repayment_periods: function(frm) {
        calculate_monthly_interest(frm);
    },

    custom_projected_sales_price: function(frm) {
        calculate_preapproval_fields(frm);
    }
});


function schedule_hbr_hydration(frm) {
    if (!frm.is_new()) return;

    hydrate_from_home_build_request(frm);

    if (hbr_defaults_complete(frm)) return;

    frm.doc.__hbr_hydration_attempts = frm.doc.__hbr_hydration_attempts || 0;
    if (frm.doc.__hbr_hydration_attempts >= 20) return;

    frm.doc.__hbr_hydration_attempts += 1;
    setTimeout(function() {
        schedule_hbr_hydration(frm);
    }, 300);
}


function hbr_defaults_complete(frm) {
    if (!frm.doc.home_build_request) return false;
    return !!(frm.doc.applicant && frm.doc.applicant_email_address &&
        frm.doc.loan_product && frm.doc.address_line_1);
}


function hydrate_from_home_build_request(frm) {
    if (!frm.is_new() || !frm.doc.home_build_request) return;
    if (frm.doc.__hbr_hydrating === frm.doc.home_build_request) return;
    if (frm.doc.__hbr_hydrated === frm.doc.home_build_request && hbr_defaults_complete(frm)) return;

    frm.doc.__hbr_hydrating = frm.doc.home_build_request;

    frappe.call({
        method: 'dcr.api.lending.get_loan_application_defaults',
        args: { home_build_request: frm.doc.home_build_request },
        callback: function(r) {
            apply_loan_application_defaults(frm, r.message || {});
            refresh_calculations(frm);
            frm.doc.__hbr_hydrated = frm.doc.home_build_request;
            frm.doc.__hbr_hydrating = null;
        },
        error: function() {
            frm.doc.__hbr_hydrating = null;
        }
    });

    frappe.db.get_doc('Home Build Request', frm.doc.home_build_request).then(function(hbr) {
        if (hbr) {
            apply_hbr_fetch_from_fields(frm, hbr, 'home_build_request');
            refresh_calculations(frm);
        }

        frappe.after_ajax(function() {
            frm.doc.__credit_fetched = false;
            frm.trigger('refresh');
        });
    });
}


function apply_loan_application_defaults(frm, defaults) {
    set_if_empty(frm, 'applicant_type', defaults.applicant_type);
    set_if_empty(frm, 'applicant', defaults.applicant);
    set_if_empty(frm, 'loan_amount', defaults.loan_amount);
    set_if_empty(frm, 'requested_advance_amount', defaults.requested_advance_amount);
    set_if_empty(frm, 'custom_quote_amount', defaults.custom_quote_amount);
    set_if_empty(frm, 'buyer_name', defaults.buyer_name);
    set_if_empty(frm, 'home_serial_no', defaults.home_serial_no);
    set_if_empty(frm, 'factory', defaults.factory);
    set_if_empty(frm, 'floor_plan', defaults.floor_plan);
    set_if_empty(frm, 'custom_monthly_space_rent', defaults.custom_monthly_space_rent);
    set_if_empty(frm, 'custom_projected_sales_price', defaults.custom_projected_sales_price);
    set_if_empty(frm, 'applicant_email_address', defaults.applicant_email_address);
    set_if_empty(frm, 'applicant_phone_number', defaults.applicant_phone_number);
    set_if_empty(frm, 'address_line_1', defaults.address_line_1);
    set_if_empty(frm, 'address_line_2', defaults.address_line_2);
    set_if_empty(frm, 'city', defaults.city);
    set_if_empty(frm, 'state', defaults.state);
    set_if_empty(frm, 'zip_code', defaults.zip_code);
    set_if_empty(frm, 'country', defaults.country);
    set_if_empty(frm, 'loan_product', defaults.loan_product);
    set_if_empty(frm, 'rate_of_interest', defaults.rate_of_interest);
    hydrate_applicant_contact(frm);
    refresh_calculations(frm);
}


function apply_hbr_fetch_from_fields(frm, hbr, link_fieldname) {
    if (!frappe.meta || !frappe.meta.get_docfields) return;
    var docfields = frappe.meta.get_docfields(frm.doc.doctype) || [];
    docfields.forEach(function(df) {
        if (!df.fetch_from || df.fetch_from.indexOf(link_fieldname + '.') !== 0) return;
        var source_field = df.fetch_from.slice(link_fieldname.length + 1);
        set_if_empty(frm, df.fieldname, hbr[source_field]);
    });
}


function hydrate_applicant_contact(frm) {
    if (!frm.doc.applicant || frm.doc.__contact_fetched_for === frm.doc.applicant) return;
    frm.doc.__contact_fetched_for = frm.doc.applicant;

    frappe.db.get_value(
        'Customer',
        frm.doc.applicant,
        ['email_id', 'mobile_no', 'customer_primary_address'],
        function(customer) {
            apply_contact_details(frm, customer);
            hydrate_applicant_address(frm, customer && customer.customer_primary_address);
            if (frm.doc.applicant_email_address && frm.doc.applicant_phone_number) return;

            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Dynamic Link',
                    filters: {
                        parenttype: 'Contact',
                        link_doctype: 'Customer',
                        link_name: frm.doc.applicant
                    },
                    fields: ['parent'],
                    limit_page_length: 1
                },
                callback: function(r) {
                    if (!r.message || !r.message.length) return;
                    frappe.db.get_value('Contact', r.message[0].parent, ['email_id', 'mobile_no'], function(contact) {
                        apply_contact_details(frm, contact);
                    });
                }
            });
        }
    );
}


function apply_contact_details(frm, details) {
    if (!details) return;
    set_if_empty(frm, 'applicant_email_address', details.email_id);
    set_if_empty(frm, 'applicant_phone_number', details.mobile_no);
}


function hydrate_applicant_address(frm, address_name) {
    if (!address_name || frm.doc.__address_fetched_for === address_name) return;
    frm.doc.__address_fetched_for = address_name;

    frappe.db.get_value(
        'Address',
        address_name,
        ['address_line1', 'address_line2', 'city', 'state', 'pincode', 'country'],
        function(address) {
            if (!address) return;
            set_if_empty(frm, 'address_line_1', address.address_line1);
            set_if_empty(frm, 'address_line_2', address.address_line2);
            set_if_empty(frm, 'city', address.city);
            set_if_empty(frm, 'state', address.state);
            set_if_empty(frm, 'zip_code', address.pincode);
            set_if_empty(frm, 'country', address.country);
        }
    );
}


function set_if_empty(frm, fieldname, value) {
    if (value === undefined || value === null || value === '') return;
    if (!frm.fields_dict[fieldname]) return;
    if (frm.doc[fieldname]) return;
    frm.set_value(fieldname, value);
}


function render_hbr_documents(frm) {
    // Mirrors the HBR's Document Checklist child table into the LA's
    // custom_hbr_documents Table field. Same child doctype, so the grid
    // renders identically to HBR's. Read-only is enforced by the field
    // itself (set read_only=1 in Customize Form). The field should be
    // is_virtual=1 so Frappe doesn't persist these mirrored rows on save.
    if (!frm.fields_dict.custom_hbr_documents) return; // field not added yet
    if (!frm.doc.home_build_request) {
        if ((frm.doc.custom_hbr_documents || []).length) {
            frm.clear_table('custom_hbr_documents');
            frm.refresh_field('custom_hbr_documents');
        }
        return;
    }

    frappe.db.get_doc('Home Build Request', frm.doc.home_build_request).then(function(hbr) {
        var target = (hbr.doc_checklist || []).map(function(r) {
            return {
                document_type: r.document_type || '',
                waived: r.waived || 0,
                attachment: r.attachment || '',
                received_date: r.received_date || ''
            };
        });
        var current = (frm.doc.custom_hbr_documents || []).map(function(r) {
            return {
                document_type: r.document_type || '',
                waived: r.waived || 0,
                attachment: r.attachment || '',
                received_date: r.received_date || ''
            };
        });
        if (JSON.stringify(current) === JSON.stringify(target)) return;

        var was_dirty = frm.is_dirty && frm.is_dirty();
        frm.clear_table('custom_hbr_documents');
        target.forEach(function(r) {
            var row = frm.add_child('custom_hbr_documents');
            row.document_type = r.document_type;
            row.waived = r.waived;
            row.attachment = r.attachment;
            row.received_date = r.received_date;
        });
        frm.refresh_field('custom_hbr_documents');
        if (!was_dirty && !frm.is_new()) {
            frm.doc.__unsaved = 0;
            frm.dirty_flag = false;
        }
    });
}


function calculate_monthly_interest(frm) {
    // DCR floor-plan loans are interest-only — monthly payment is just
    // the accruing interest, principal balloons at payoff. Mirrors the
    // server-side override in validate_loan_application so the preview
    // matches what saves.
    var rate = frm.doc.rate_of_interest || 0;
    var amount = frm.doc.loan_amount || 0;
    var periods = frm.doc.repayment_periods || 0;

    if (rate && amount) {
        var monthly = (rate / 100) * amount / 12;
        set_calculated_value(frm, 'repayment_amount', monthly);
        if (periods) {
            var total_interest = monthly * periods;
            set_calculated_value(frm, 'total_payable_interest', total_interest);
            set_calculated_value(frm, 'total_payable_amount', amount + total_interest);
        } else {
            set_calculated_value(frm, 'total_payable_interest', null);
            set_calculated_value(frm, 'total_payable_amount', null);
        }
    } else {
        set_calculated_value(frm, 'repayment_amount', null);
        set_calculated_value(frm, 'total_payable_interest', null);
        set_calculated_value(frm, 'total_payable_amount', null);
    }
}


function calculate_preapproval_fields(frm) {
    var sales_price = frm.doc.custom_projected_sales_price || 0;
    var loan_amount = frm.doc.loan_amount || 0;

    if (sales_price && loan_amount) {
        set_calculated_value(frm, 'custom_projected_equity', sales_price - loan_amount);
        set_calculated_value(frm, 'custom_projected_ltv', (loan_amount / sales_price) * 100);
    } else {
        set_calculated_value(frm, 'custom_projected_equity', null);
        set_calculated_value(frm, 'custom_projected_ltv', null);
    }
}


function refresh_calculations(frm) {
    // Submitted applications are snapshots. Their values come from the
    // validate hook and should not be re-written by a browser refresh.
    if (frm.doc.docstatus && frm.doc.docstatus !== 0) return;
    calculate_monthly_interest(frm);
    calculate_preapproval_fields(frm);
}


function set_calculated_value(frm, fieldname, value) {
    if (!frm.fields_dict[fieldname]) return;
    var current = frm.doc[fieldname];
    if (value === null || value === undefined) {
        if (current !== null && current !== undefined && current !== '') {
            frm.set_value(fieldname, null);
        }
        return;
    }
    if (Math.abs(parseFloat(current || 0) - value) > 0.000001) {
        frm.set_value(fieldname, value);
    }
}


function send_flooring_packet(frm) {
    frappe.db.get_value('Customer', frm.doc.applicant, 'email_id', function(r) {
        if (!r || !r.email_id) {
            frappe.msgprint(__('Customer {0} does not have an email address.', [frm.doc.applicant]));
            return;
        }

        frappe.confirm(
            __('Send Flooring Packet (Info Sheet + Exhibit A + Auto-Pay Authorization) to {0} ({1}) for signature?',
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
