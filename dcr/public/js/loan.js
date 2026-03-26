/**
 * Loan Form Customization for ACH Autopay
 *
 * Buttons:
 * - Email → "Disbursement Notice" — notify dealer of disbursement
 * - Email → "FL Payoff Letter" / "COD Payoff Letter" — payoff letters
 * - Actions → "Manage Auto-Pay" — ACH setup via Plaid or manual
 */

frappe.ui.form.on('Loan', {
    refresh: function(frm) {
        // Only show for submitted loans
        if (frm.doc.docstatus !== 1) {
            return;
        }

        // Email: Disbursement Notice — show if any disbursement exists
        frappe.db.count('Loan Disbursement', {
            filters: { against_loan: frm.doc.name, docstatus: 1 }
        }).then(count => {
            if (count > 0) {
                frm.add_custom_button(__('Disbursement Notice'), function() {
                    send_disbursement_notice(frm);
                }, __('Email'));
            }
        });

        // Email: Payoff letter buttons — only for disbursed/active loans
        if (frm.doc.status && ['Disbursed', 'Active'].includes(frm.doc.status)) {
            frm.add_custom_button(__('FL Payoff Letter'), function() {
                send_payoff(frm, 'Flooring');
            }, __('Email'));

            frm.add_custom_button(__('COD Payoff Letter'), function() {
                send_payoff(frm, 'COD');
            }, __('Email'));
        }

        // Actions: Manage Auto-Pay
        frappe.call({
            method: 'dcr.dcr.doctype.ach_settings.ach_settings.is_ach_enabled',
            callback: function(r) {
                if (r.message) {
                    frm.add_custom_button(__('Manage Auto-Pay'), function() {
                        show_autopay_manager(frm);
                    }, __('Actions'));
                }
            }
        });
    }
});


function show_autopay_manager(frm) {
    // Get customer's bank accounts and loan's current payment account
    Promise.all([
        frappe.call({
            method: 'dcr.api.achq_integration.get_customer_accounts',
            args: { customer: frm.doc.applicant }
        }),
        frappe.call({
            method: 'dcr.api.achq_integration.get_loan_account_info',
            args: { loan: frm.doc.name }
        }),
        frappe.call({
            method: 'dcr.api.achq_integration.is_plaid_available'
        })
    ]).then(function([accounts_r, loan_r, plaid_r]) {
        const accounts = (accounts_r.message && accounts_r.message.accounts) || [];
        const loan_account = loan_r.message || {};
        const plaid_available = plaid_r.message && plaid_r.message.available;

        show_autopay_dialog(frm, accounts, loan_account, plaid_available);
    });
}


function show_autopay_dialog(frm, accounts, loan_account, plaid_available) {
    let accounts_html = '';

    if (accounts.length === 0) {
        accounts_html = `
            <div class="text-muted text-center" style="padding: 20px;">
                <p>No bank accounts set up yet.</p>
                <p>Add a bank account below, or send the dealer a link to connect.</p>
                <button class="btn btn-default btn-sm btn-send-setup-email" style="margin-top: 8px;">
                    <i class="fa fa-envelope-o"></i> Send Setup Email to Dealer
                </button>
            </div>
        `;
    } else {
        accounts_html = '<div class="bank-accounts-list">';
        for (const acc of accounts) {
            const is_current = loan_account.has_account && loan_account.authorization_name === acc.name;
            const is_default = acc.is_default;
            const status_color = acc.status === 'Active' ? 'green' : 'orange';

            let badges = '';
            if (is_default) badges += '<span class="badge badge-primary">Default</span> ';
            if (is_current) badges += '<span class="badge badge-success">Using for this loan</span>';
            if (acc.token_source === 'Plaid') badges += ' <span class="badge badge-info">Plaid</span>';

            accounts_html += `
                <div class="bank-account-item" data-auth="${acc.name}" style="border: 1px solid #d1d8dd; border-radius: 4px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>${acc.bank_name || 'Bank Account'}</strong> ending in ${acc.bank_account_last4}
                            <br>
                            <small class="text-muted">${acc.account_type} &bull; <span class="indicator-pill ${status_color}">${acc.status}</span></small>
                            <br>
                            ${badges}
                        </div>
                        <div class="account-actions">
                            ${!is_current ? `<button class="btn btn-xs btn-primary use-for-loan" data-auth="${acc.name}">Use for This Loan</button>` : ''}
                            ${!is_default && acc.status === 'Active' ? `<button class="btn btn-xs btn-default set-default" data-auth="${acc.name}">Set as Default</button>` : ''}
                            <button class="btn btn-xs btn-danger remove-account" data-auth="${acc.name}">Remove</button>
                        </div>
                    </div>
                </div>
            `;
        }
        accounts_html += '</div>';
    }

    // Show resolution info
    let resolution_html = '';
    if (loan_account.has_account) {
        const resolution_text = loan_account.resolution === 'loan_override'
            ? 'This loan uses a specific account override'
            : 'This loan uses the customer\'s default account';
        resolution_html = `
            <div class="alert alert-info" style="margin-bottom: 15px;">
                <strong>Current Payment Account:</strong> ${loan_account.bank_name || 'Bank'} ending in ${loan_account.account_last4}
                <br><small>${resolution_text}</small>
                ${loan_account.resolution === 'loan_override' ? '<br><button class="btn btn-xs btn-default clear-override" style="margin-top: 5px;">Use Default Instead</button>' : ''}
            </div>
        `;
    } else {
        resolution_html = `
            <div class="alert alert-warning" style="margin-bottom: 15px;">
                <strong>No Payment Account:</strong> Add a bank account to enable automatic payments.
            </div>
        `;
    }

    const dialog = new frappe.ui.Dialog({
        title: __('Manage Auto-Pay'),
        size: 'large',
        fields: [
            {
                fieldname: 'accounts_html',
                fieldtype: 'HTML',
                options: resolution_html + accounts_html
            },
            {
                fieldname: 'add_section',
                fieldtype: 'Section Break',
                label: 'Add Bank Account'
            },
            {
                fieldname: 'add_buttons_html',
                fieldtype: 'HTML',
                options: `
                    <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                        ${plaid_available ?
                            `<button class="btn btn-primary btn-plaid">
                                <i class="fa fa-university"></i> Connect with Plaid
                            </button>` : ''}
                        <button class="btn btn-default btn-manual">
                            <i class="fa fa-keyboard-o"></i> Enter Manually
                        </button>
                    </div>
                `
            }
        ]
    });

    dialog.show();

    // Bind button events
    dialog.$wrapper.find('.btn-plaid').on('click', function() {
        dialog.hide();
        start_plaid_link(frm);
    });

    dialog.$wrapper.find('.btn-manual').on('click', function() {
        dialog.hide();
        show_manual_entry_dialog(frm);
    });

    dialog.$wrapper.find('.use-for-loan').on('click', function() {
        const auth_name = $(this).data('auth');
        set_loan_account(frm, auth_name, dialog);
    });

    dialog.$wrapper.find('.set-default').on('click', function() {
        const auth_name = $(this).data('auth');
        set_default_account(auth_name, dialog, frm);
    });

    dialog.$wrapper.find('.remove-account').on('click', function() {
        const auth_name = $(this).data('auth');
        confirm_remove_account(auth_name, dialog, frm);
    });

    dialog.$wrapper.find('.clear-override').on('click', function() {
        clear_loan_override(frm, dialog);
    });

    dialog.$wrapper.find('.btn-send-setup-email').on('click', function() {
        frappe.call({
            method: 'dcr.api.dcr_email.send_autopay_update_email',
            args: { customer: frm.doc.applicant },
            freeze: true,
            freeze_message: __('Sending email...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __('Setup email sent to dealer'),
                        indicator: 'green'
                    });
                }
            }
        });
    });
}


function start_plaid_link(frm) {
    frappe.call({
        method: 'dcr.api.achq_integration.get_plaid_link_token',
        args: { customer: frm.doc.applicant },
        callback: function(r) {
            if (r.message && r.message.success) {
                open_plaid_link(frm, r.message.link_token);
            }
        }
    });
}


function open_plaid_link(frm, link_token) {
    if (typeof Plaid === 'undefined') {
        const script = document.createElement('script');
        script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
        script.onload = function() {
            create_plaid_handler(frm, link_token);
        };
        document.head.appendChild(script);
    } else {
        create_plaid_handler(frm, link_token);
    }
}


function create_plaid_handler(frm, link_token) {
    const handler = Plaid.create({
        token: link_token,
        onSuccess: function(public_token, metadata) {
            if (!metadata.accounts || metadata.accounts.length === 0) {
                frappe.msgprint(__('No account was selected. Please try again.'));
                show_autopay_manager(frm);
                return;
            }
            const account = metadata.accounts[0];
            process_plaid_success(frm, public_token, account.id);
        },
        onExit: function(err, metadata) {
            if (err) {
                frappe.confirm(
                    __("Couldn't connect to your bank. Would you like to enter your account details manually?"),
                    function() {
                        show_manual_entry_dialog(frm);
                    }
                );
            }
            show_autopay_manager(frm);
        },
        onEvent: function(eventName, metadata) {
            // Optional: log events for debugging
        }
    });

    handler.open();
}


function process_plaid_success(frm, public_token, account_id) {
    frappe.call({
        method: 'dcr.api.achq_integration.process_plaid_callback',
        args: {
            public_token: public_token,
            account_id: account_id,
            customer: frm.doc.applicant,
            is_default: true
        },
        freeze: true,
        freeze_message: __('Connecting bank account...'),
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: __('Bank account connected: {0} ending in {1}',
                        [r.message.bank_name, r.message.account_last4]),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}


function show_manual_entry_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __('Add Bank Account Manually'),
        fields: [
            {
                fieldname: 'info_html',
                fieldtype: 'HTML',
                options: `
                    <div class="alert alert-info">
                        <p>Enter your bank account details below. Your account will be verified before activation.</p>
                    </div>
                `
            },
            {
                fieldname: 'routing_number',
                fieldtype: 'Data',
                label: __('Routing Number'),
                reqd: 1,
                description: __('9-digit bank routing number')
            },
            {
                fieldname: 'account_number',
                fieldtype: 'Data',
                label: __('Account Number'),
                reqd: 1
            },
            {
                fieldname: 'confirm_account_number',
                fieldtype: 'Data',
                label: __('Confirm Account Number'),
                reqd: 1
            },
            {
                fieldname: 'account_type',
                fieldtype: 'Select',
                label: __('Account Type'),
                options: 'Checking\nSavings',
                default: 'Checking',
                reqd: 1
            },
            {
                fieldname: 'is_default',
                fieldtype: 'Check',
                label: __('Set as default payment account'),
                default: 1
            },
            {
                fieldname: 'consent_section',
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'consent',
                fieldtype: 'Check',
                label: __('I authorize DCR to initiate ACH debit entries from the business bank account specified above for loan repayment obligations.'),
                reqd: 1
            }
        ],
        primary_action_label: __('Add Account'),
        primary_action: function(values) {
            if (!validate_manual_entry(values)) {
                return;
            }

            dialog.disable_primary_action();

            frappe.call({
                method: 'dcr.api.achq_integration.setup_bank_account',
                args: {
                    customer: frm.doc.applicant,
                    routing_number: values.routing_number,
                    account_number: values.account_number,
                    account_type: values.account_type,
                    is_default: values.is_default
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        dialog.hide();
                        frappe.show_alert({
                            message: __('Bank account added: ending in {0}', [r.message.account_last4]),
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    }
                },
                error: function() {
                    dialog.enable_primary_action();
                }
            });
        },
        secondary_action_label: __('Back'),
        secondary_action: function() {
            dialog.hide();
            show_autopay_manager(frm);
        }
    });

    dialog.show();
}


function validate_manual_entry(values) {
    const routing = values.routing_number.replace(/\D/g, '');
    if (routing.length !== 9) {
        frappe.msgprint(__('Routing number must be exactly 9 digits'));
        return false;
    }

    if (values.account_number !== values.confirm_account_number) {
        frappe.msgprint(__('Account numbers do not match'));
        return false;
    }

    const account = values.account_number.replace(/\D/g, '');
    if (account.length < 4 || account.length > 17) {
        frappe.msgprint(__('Account number must be between 4 and 17 digits'));
        return false;
    }

    if (!values.consent) {
        frappe.msgprint(__('Please accept the authorization consent'));
        return false;
    }

    return true;
}


function set_loan_account(frm, auth_name, dialog) {
    frappe.call({
        method: 'dcr.api.achq_integration.set_loan_account',
        args: {
            loan: frm.doc.name,
            authorization_name: auth_name
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                dialog.hide();
                frappe.show_alert({
                    message: __('Payment account updated for this loan'),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}


function clear_loan_override(frm, dialog) {
    frappe.call({
        method: 'dcr.api.achq_integration.set_loan_account',
        args: {
            loan: frm.doc.name,
            authorization_name: ''
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                dialog.hide();
                frappe.show_alert({
                    message: __('This loan will now use the default payment account'),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}


function set_default_account(auth_name, dialog, frm) {
    frappe.call({
        method: 'dcr.api.achq_integration.set_default_account',
        args: {
            authorization_name: auth_name
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                dialog.hide();
                frappe.show_alert({
                    message: __('Default payment account updated'),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}


function confirm_remove_account(auth_name, dialog, frm) {
    frappe.confirm(
        __('Are you sure you want to remove this bank account? Any scheduled payments using this account will be affected.'),
        function() {
            frappe.prompt([
                {
                    fieldname: 'reason',
                    fieldtype: 'Small Text',
                    label: __('Reason (optional)')
                }
            ], function(values) {
                frappe.call({
                    method: 'dcr.api.achq_integration.revoke_authorization',
                    args: {
                        authorization_name: auth_name,
                        reason: values.reason
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            dialog.hide();
                            frappe.show_alert({
                                message: __('Bank account removed'),
                                indicator: 'red'
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Remove Bank Account'), __('Remove'));
        }
    );
}


function send_disbursement_notice(frm) {
    frappe.db.get_value('Customer', frm.doc.applicant, 'email_id', function(r) {
        if (!r || !r.email_id) {
            frappe.msgprint(__('Customer {0} does not have an email address.', [frm.doc.applicant]));
            return;
        }

        frappe.confirm(
            __('Send Disbursement Notice to {0} ({1})?', [frm.doc.applicant, r.email_id]),
            function() {
                frappe.call({
                    method: 'dcr.api.dcr_email.send_loan_disbursed',
                    args: {
                        customer_name: frm.doc.applicant_name || frm.doc.applicant,
                        factory_name: frm.doc.factory || '',
                        loan: frm.doc.name,
                        home_build_request: frm.doc.home_serial_no || '',
                        amount: frm.doc.loan_amount,
                        to_email: r.email_id,
                        reference_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Sending disbursement notice...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Disbursement Notice sent'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            }
        );
    });
}


function send_payoff(frm, payoff_type) {
    frappe.confirm(
        __('Send {0} Payoff Letter to {1}?', [payoff_type, frm.doc.applicant]),
        function() {
            frappe.call({
                method: 'dcr.api.docusign.send_payoff_letter',
                args: { loan: frm.doc.name, payoff_type: payoff_type },
                freeze: true,
                freeze_message: __('Sending payoff letter...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('{0} Payoff Letter sent', [payoff_type]),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    );
}
