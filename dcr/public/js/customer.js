/**
 * Customer Form Customization for DCR Dealers
 *
 * Buttons:
 * - Email → "Dealer Agreement" — Dealer Agreement via DocuSign
 * - Create → MIFA — after dealer agreement is signed
 * - Create → Factory Assignment — if none exists
 * - Actions → "Manage Bank Account" — ACH setup via Plaid or manual
 */

frappe.ui.form.on('Customer', {
    refresh: function(frm) {
        if (frm.doc.customer_group !== 'Dealer' || frm.is_new()) {
            return;
        }

        // Signing status indicator
        if (frm.doc.dealer_agreement_status === 'Signed') {
            frm.page.set_indicator(__('Agreement Signed'), 'green');
        } else if (frm.doc.dealer_agreement_status === 'Sent') {
            frm.page.set_indicator(__('Awaiting Signature'), 'orange');
        }

        // Email: Dealer Agreement (for signature)
        if (frm.doc.dealer_agreement_status !== 'Signed') {
            frm.add_custom_button(__('Dealer Agreement'), function() {
                send_dealer_agreement(frm);
            }, __('Email'));
        }

        // Create → MIFA (after dealer agreement is signed)
        if (frm.doc.dealer_agreement_status === 'Signed') {
            frappe.db.count('MIFA', { customer: frm.doc.name }).then(function(count) {
                if (count === 0) {
                    frm.add_custom_button(__('MIFA'), function() {
                        frappe.new_doc('MIFA', {
                            customer: frm.doc.name
                        });
                    }, __('Create'));
                    frm.change_custom_button_type(__('MIFA'), __('Create'), 'primary');
                }
            });
        }

        // Create → Factory Assignment (multiple allowed per dealer)
        frm.add_custom_button(__('Factory Assignment'), function() {
            frappe.new_doc('Factory Assignment', {
                customer: frm.doc.name
            });
        }, __('Create'));

        // Actions: Manage Bank Account + Send Bank Update Email
        frappe.call({
            method: 'dcr.dcr.doctype.ach_settings.ach_settings.is_ach_enabled',
            callback: function(r) {
                if (r.message) {
                    frm.add_custom_button(__('Manage Bank Account'), function() {
                        show_bank_account_manager(frm);
                    }, __('Actions'));

                    frm.add_custom_button(__('Send Bank Update Email'), function() {
                        send_bank_update_email(frm);
                    }, __('Actions'));
                }
            }
        });
    }
});


function send_dealer_agreement(frm) {
    if (!frm.doc.email_id) {
        frappe.msgprint(__('Please set an email address for this customer before sending the agreement.'));
        return;
    }

    frappe.confirm(
        __('Send Dealer Agreement to {0}?', [frm.doc.email_id]),
        function() {
            frappe.call({
                method: 'dcr.api.docusign.send_dealer_agreement',
                args: { customer: frm.doc.name },
                freeze: true,
                freeze_message: __('Sending agreement...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Dealer Agreement sent for signature'),
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}


function show_bank_account_manager(frm) {
    Promise.all([
        frappe.call({
            method: 'dcr.api.achq_integration.get_customer_accounts',
            args: { customer: frm.doc.name }
        }),
        frappe.call({
            method: 'dcr.api.achq_integration.is_plaid_available'
        })
    ]).then(function([accounts_r, plaid_r]) {
        const accounts = (accounts_r.message && accounts_r.message.accounts) || [];
        const plaid_available = plaid_r.message && plaid_r.message.available;

        show_bank_dialog(frm, accounts, plaid_available);
    });
}


function show_bank_dialog(frm, accounts, plaid_available) {
    let accounts_html = '';

    if (accounts.length === 0) {
        accounts_html = `
            <div class="text-muted text-center" style="padding: 20px;">
                <p>No bank accounts linked yet.</p>
                <p>Add a bank account to enable ACH autopay for this dealer.</p>
            </div>
        `;
    } else {
        accounts_html = '<div class="bank-accounts-list">';
        for (const acc of accounts) {
            const status_color = acc.status === 'Active' ? 'green' : 'orange';
            let badges = '';
            if (acc.is_default) badges += '<span class="badge badge-primary">Default</span> ';
            if (acc.token_source === 'Plaid') badges += '<span class="badge badge-info">Plaid</span>';

            accounts_html += `
                <div class="bank-account-item" style="border: 1px solid #d1d8dd; border-radius: 4px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>${acc.bank_name || 'Bank Account'}</strong> ending in ${acc.bank_account_last4}
                            <br>
                            <small class="text-muted">${acc.account_type} &bull; <span class="indicator-pill ${status_color}">${acc.status}</span></small>
                            <br>${badges}
                        </div>
                        <div>
                            ${!acc.is_default && acc.status === 'Active' ? `<button class="btn btn-xs btn-default set-default" data-auth="${acc.name}">Set as Default</button>` : ''}
                            <button class="btn btn-xs btn-danger remove-account" data-auth="${acc.name}">Remove</button>
                        </div>
                    </div>
                </div>
            `;
        }
        accounts_html += '</div>';
    }

    const dialog = new frappe.ui.Dialog({
        title: __('Manage Bank Account'),
        size: 'large',
        fields: [
            {
                fieldname: 'accounts_html',
                fieldtype: 'HTML',
                options: accounts_html
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

    dialog.$wrapper.find('.btn-plaid').on('click', function() {
        dialog.hide();
        start_plaid_link_customer(frm);
    });

    dialog.$wrapper.find('.btn-manual').on('click', function() {
        dialog.hide();
        show_manual_entry_customer(frm);
    });

    dialog.$wrapper.find('.set-default').on('click', function() {
        const auth_name = $(this).data('auth');
        frappe.call({
            method: 'dcr.api.achq_integration.set_default_account',
            args: { authorization_name: auth_name },
            callback: function(r) {
                if (r.message && r.message.success) {
                    dialog.hide();
                    frappe.show_alert({ message: __('Default account updated'), indicator: 'green' });
                    frm.reload_doc();
                }
            }
        });
    });

    dialog.$wrapper.find('.remove-account').on('click', function() {
        const auth_name = $(this).data('auth');
        frappe.confirm(__('Remove this bank account?'), function() {
            frappe.call({
                method: 'dcr.api.achq_integration.revoke_authorization',
                args: { authorization_name: auth_name },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        dialog.hide();
                        frappe.show_alert({ message: __('Account removed'), indicator: 'red' });
                        frm.reload_doc();
                    }
                }
            });
        });
    });
}


function start_plaid_link_customer(frm) {
    frappe.call({
        method: 'dcr.api.achq_integration.get_plaid_link_token',
        args: { customer: frm.doc.name },
        callback: function(r) {
            if (r.message && r.message.success) {
                open_plaid_link_customer(frm, r.message.link_token);
            }
        }
    });
}


function open_plaid_link_customer(frm, link_token) {
    if (typeof Plaid === 'undefined') {
        const script = document.createElement('script');
        script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
        script.onload = function() { _create_plaid_handler(frm, link_token); };
        document.head.appendChild(script);
    } else {
        _create_plaid_handler(frm, link_token);
    }
}


function _create_plaid_handler(frm, link_token) {
    const handler = Plaid.create({
        token: link_token,
        onSuccess: function(public_token, metadata) {
            if (!metadata.accounts || metadata.accounts.length === 0) {
                frappe.msgprint(__('No account was selected.'));
                return;
            }
            frappe.call({
                method: 'dcr.api.achq_integration.process_plaid_callback',
                args: {
                    public_token: public_token,
                    account_id: metadata.accounts[0].id,
                    customer: frm.doc.name,
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
        },
        onExit: function(err) {
            if (err) {
                frappe.confirm(
                    __("Couldn't connect to bank. Enter details manually?"),
                    function() { show_manual_entry_customer(frm); }
                );
            }
        }
    });
    handler.open();
}


function show_manual_entry_customer(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __('Add Bank Account'),
        fields: [
            { fieldname: 'routing_number', fieldtype: 'Data', label: __('Routing Number'), reqd: 1, description: __('9-digit bank routing number') },
            { fieldname: 'account_number', fieldtype: 'Data', label: __('Account Number'), reqd: 1 },
            { fieldname: 'confirm_account_number', fieldtype: 'Data', label: __('Confirm Account Number'), reqd: 1 },
            { fieldname: 'account_type', fieldtype: 'Select', label: __('Account Type'), options: 'Checking\nSavings', default: 'Checking', reqd: 1 },
            { fieldname: 'consent_section', fieldtype: 'Section Break' },
            {
                fieldname: 'consent', fieldtype: 'Check', reqd: 1,
                label: __('I authorize DCR to initiate ACH debit entries from the business bank account specified above for loan repayment obligations.')
            }
        ],
        primary_action_label: __('Add Account'),
        primary_action: function(values) {
            const routing = values.routing_number.replace(/\D/g, '');
            if (routing.length !== 9) { frappe.msgprint(__('Routing number must be 9 digits')); return; }
            if (values.account_number !== values.confirm_account_number) { frappe.msgprint(__('Account numbers do not match')); return; }

            dialog.disable_primary_action();
            frappe.call({
                method: 'dcr.api.achq_integration.setup_bank_account',
                args: {
                    customer: frm.doc.name,
                    routing_number: values.routing_number,
                    account_number: values.account_number,
                    account_type: values.account_type,
                    is_default: true
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        dialog.hide();
                        frappe.show_alert({ message: __('Bank account added'), indicator: 'green' });
                        frm.reload_doc();
                    }
                },
                error: function() { dialog.enable_primary_action(); }
            });
        }
    });
    dialog.show();
}


function send_bank_update_email(frm) {
    if (!frm.doc.email_id) {
        frappe.msgprint(__('Please set an email address for this customer first.'));
        return;
    }

    frappe.confirm(
        __('Send bank account update email to {0} ({1})?', [frm.doc.customer_name, frm.doc.email_id]),
        function() {
            frappe.call({
                method: 'dcr.api.dcr_email.send_autopay_update_email',
                args: { customer: frm.doc.name },
                freeze: true,
                freeze_message: __('Sending email...'),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Bank update email sent to {0}', [frm.doc.email_id]),
                            indicator: 'green'
                        });
                    }
                }
            });
        }
    );
}
