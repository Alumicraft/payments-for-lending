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

    refresh: function(frm) {
        // Force-show read-only fields (Frappe v15 hides empty read-only fields on new forms)
        ['rate_of_interest', 'buyer_name', 'available_credit', 'outstanding_loan_balance',
         'custom_current_yn', 'repayment_amount',
         'total_payable_amount', 'total_payable_interest', 'custom_projected_equity',
         'custom_projected_ltv', 'custom_monthly_space_rent'].forEach(function(fn) {
            var field = frm.fields_dict[fn];
            if (field && field.$wrapper) field.$wrapper.show();
        });

        // Run client-side calcs once with whatever values are in scope
        // (handles fetch_from populating rate_of_interest etc. without a
        // user keystroke firing the field handler).
        calculate_monthly_interest(frm);
        calculate_preapproval_fields(frm);

        // Fetch loan product + credit info when applicant is set
        if (frm.doc.applicant) {
            if (!frm.doc.loan_product) {
                frappe.db.get_value('Customer', frm.doc.applicant, 'default_loan_product', function(r) {
                    if (r && r.default_loan_product) {
                        frm.set_value('loan_product', r.default_loan_product);
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
        if (frm.doc.docstatus === 1) {
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
        }
    },

    applicant: function(frm) {
        // Clear fetch cache so credit info re-runs for new applicant
        frm.doc.__credit_fetched = false;
        frm.trigger('refresh');
    },

    home_build_request: function(frm) {
        // fetch_from silently populates applicant without firing the applicant handler
        // so we manually clear cache and re-run credit fetches after HBR is linked
        frappe.after_ajax(function() {
            frm.doc.__credit_fetched = false;
            frm.trigger('refresh');
        });
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


function render_hbr_documents(frm) {
    // Mirrors the HBR's Document Checklist child table into the LA's
    // custom_hbr_documents Table field. Same child doctype, so the grid
    // renders identically to HBR's. Read-only is enforced by the field
    // itself (set read_only=1 in Customize Form). The field should be
    // is_virtual=1 so Frappe doesn't persist these mirrored rows on save.
    if (!frm.fields_dict.custom_hbr_documents) return; // field not added yet
    if (!frm.doc.home_build_request) {
        frm.clear_table('custom_hbr_documents');
        frm.refresh_field('custom_hbr_documents');
        return;
    }

    frappe.db.get_doc('Home Build Request', frm.doc.home_build_request).then(function(hbr) {
        frm.clear_table('custom_hbr_documents');
        (hbr.doc_checklist || []).forEach(function(r) {
            var row = frm.add_child('custom_hbr_documents');
            row.document_type = r.document_type;
            row.waived = r.waived;
            row.attachment = r.attachment;
            row.received_date = r.received_date;
        });
        frm.refresh_field('custom_hbr_documents');
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
        frm.set_value('repayment_amount', monthly);
        if (periods) {
            var total_interest = monthly * periods;
            frm.set_value('total_payable_interest', total_interest);
            frm.set_value('total_payable_amount', amount + total_interest);
        } else {
            frm.set_value('total_payable_interest', null);
            frm.set_value('total_payable_amount', null);
        }
    } else {
        frm.set_value('repayment_amount', null);
        frm.set_value('total_payable_interest', null);
        frm.set_value('total_payable_amount', null);
    }
}


function calculate_preapproval_fields(frm) {
    var sales_price = frm.doc.custom_projected_sales_price || 0;
    var loan_amount = frm.doc.loan_amount || 0;

    if (sales_price && loan_amount) {
        frm.set_value('custom_projected_equity', sales_price - loan_amount);
        frm.set_value('custom_projected_ltv', (loan_amount / sales_price) * 100);
    } else {
        frm.set_value('custom_projected_equity', null);
        frm.set_value('custom_projected_ltv', null);
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
