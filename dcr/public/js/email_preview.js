/**
 * DCR email preview affordance.
 *
 * The Email app owns the actual send pipeline (and its API-key/permission
 * checks). This small form action lets an operator inspect the recipient,
 * subject, body, and PDF attachment first, then hands the unchanged values to
 * the Email app's send API.
 */
(function() {
    "use strict";

    function add_preview_button(frm) {
        if (frm.doc.docstatus !== 1) return;
        if (frm.custom_buttons && frm.custom_buttons[__('Preview Email')]) return;

        frm.add_custom_button(__('Preview Email'), function() {
            show_email_preview(frm);
        }, __('Email'));
    }

    frappe.ui.form.on('Purchase Order', {
        refresh: function(frm) {
            add_preview_button(frm);
            hydrate_payment_type(frm);
        },
        custom_home_build_request: hydrate_payment_type
    });

    function hydrate_payment_type(frm) {
        if (!frm.fields_dict.custom_payment_type || !frm.doc.custom_home_build_request) return;
        if (frm.doc.custom_payment_type) return;
        // A submitted PO must remain a clean, read-only document. The email
        // preview derives this value from the linked HBR when the field is
        // blank, so do not mark the submitted form dirty just for display.
        if (frm.doc.docstatus === 1) return;

        frappe.db.get_value(
            'Home Build Request',
            frm.doc.custom_home_build_request,
            'financing_type',
            function(r) {
                if (!r || !r.financing_type || frm.doc.custom_payment_type) return;
                frm.set_value(
                    'custom_payment_type',
                    r.financing_type === 'Floored' ? 'Flooring' : 'COD'
                );
            }
        );
    }

    function show_email_preview(frm) {
        frappe.call({
            method: 'dcr.api.dcr_email.preview_document_email',
            args: {
                doctype: frm.doctype,
                docname: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Preparing email preview...'),
            callback: function(r) {
                if (!r.message || !r.message.success) {
                    frappe.msgprint({
                        title: __('Email Preview Unavailable'),
                        message: r.message && r.message.message || __('Could not prepare the email preview.'),
                        indicator: 'orange'
                    });
                    return;
                }
                open_preview_dialog(frm, r.message);
            }
        });
    }

    function open_preview_dialog(frm, preview) {
        var dialog = new frappe.ui.Dialog({
            title: __('Preview Email'),
            size: 'extra-large',
            fields: [
                {
                    fieldname: 'to_email',
                    fieldtype: 'Data',
                    label: __('Recipient Email'),
                    options: 'Email',
                    reqd: 1,
                    default: preview.recipient || ''
                },
                {
                    fieldname: 'cc',
                    fieldtype: 'Data',
                    label: __('CC'),
                    options: 'Email'
                },
                {
                    fieldname: 'bcc',
                    fieldtype: 'Data',
                    label: __('BCC'),
                    options: 'Email'
                },
                {
                    fieldname: 'custom_message',
                    fieldtype: 'Small Text',
                    label: __('Custom Message')
                },
                {
                    fieldname: 'preview_subject',
                    fieldtype: 'Data',
                    label: __('Subject'),
                    read_only: 1,
                    default: preview.subject || ''
                },
                {
                    fieldname: 'preview_body',
                    fieldtype: 'HTML',
                    options: preview.body || ''
                },
                {
                    fieldname: 'preview_attachment',
                    fieldtype: 'HTML',
                    options: attachment_label(preview)
                }
            ],
            primary_action_label: __('Send Email'),
            primary_action: function(values) {
                dialog.hide();
                send_email(frm, values);
            }
        });

        dialog.set_secondary_action(function() {
            var values = dialog.get_values() || {};
            refresh_preview(dialog, frm, values);
        });
        dialog.set_secondary_action_label(__('Refresh Preview'));
        dialog.show();
    }

    function refresh_preview(dialog, frm, values) {
        frappe.call({
            method: 'dcr.api.dcr_email.preview_document_email',
            args: {
                doctype: frm.doctype,
                docname: frm.doc.name,
                to_email: values.to_email,
                custom_message: values.custom_message
            },
            freeze: true,
            freeze_message: __('Refreshing preview...'),
            callback: function(r) {
                if (!r.message || !r.message.success) {
                    frappe.msgprint(r.message && r.message.message || __('Could not refresh the preview.'));
                    return;
                }
                dialog.set_value('preview_subject', r.message.subject || '');
                dialog.fields_dict.preview_body.$wrapper.html(r.message.body || '');
                dialog.fields_dict.preview_attachment.$wrapper.html(attachment_label(r.message));
            }
        });
    }

    function attachment_label(preview) {
        var attachments = preview.attachments || [];
        if (!attachments.length) return '<div class="text-muted">' + __('No attachment') + '</div>';
        return '<div class="text-muted"><strong>' + __('Attachment:') + '</strong> ' +
            escape_html(attachments[0].filename || __('PDF')) + '</div>';
    }

    function escape_html(value) {
        return $('<div>').text(value).html();
    }

    function send_email(frm, values) {
        var method = frm.doctype === 'Purchase Order'
            ? 'dcr.api.dcr_email.send_purchase_order_email'
            : 'emails.api.send_document_email';
        var args = {
            doctype: frm.doctype,
            docname: frm.doc.name,
            to_email: values.to_email,
            cc: values.cc,
            bcc: values.bcc,
            custom_message: values.custom_message
        };
        if (frm.doctype === 'Purchase Order') {
            args = {
                purchase_order: frm.doc.name,
                to_email: values.to_email,
                cc: values.cc,
                bcc: values.bcc,
                custom_message: values.custom_message
            };
        }
        frappe.call({
            method: method,
            args: args,
            freeze: true,
            freeze_message: __('Sending email...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __('Email sent successfully'),
                        indicator: 'green'
                    });
                    frm.reload_doc();
                    return;
                }
                frappe.msgprint({
                    title: __('Email Failed'),
                    message: r.message && r.message.message || __('The email service could not send this message.'),
                    indicator: 'red'
                });
            }
        });
    }
})();
