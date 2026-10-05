/* Review the recipient and exact cached PDFs before creating an envelope. */
frappe.provide('dcr');
dcr.preview_signature = async function(frm, document_type, method, reference_argument) {
    if (frm.is_dirty() || frm.is_new()) {
        frappe.msgprint(__('Save this record before reviewing documents.'));
        return;
    }
    const {message: preview} = await frappe.call({
        method: 'dcr.api.docusign.preview_signature',
        args: {document_type, reference_name: frm.doc.name},
        freeze: true, freeze_message: __('Preparing document preview...')
    });
    if (!preview) return;
    const dialog = new frappe.ui.Dialog({
        title: __('Review {0}', [document_type]), size: 'extra-large',
        fields: [{fieldname: 'review', fieldtype: 'HTML'},
            {fieldname: 'reviewed', fieldtype: 'Check', label: __('I reviewed all documents and the recipient'), reqd: 1}],
        primary_action_label: __('Send for signature'),
        primary_action: async function(values) {
            if (!values.reviewed) return;
            dialog.disable_primary_action();
            try {
                const {message} = await frappe.call({method,
                    args: {[reference_argument]: frm.doc.name, review_token: preview.review_token},
                    freeze: true, freeze_message: __('Sending reviewed documents...')});
                if (message && message.success) {
                    dialog.hide();
                    frappe.show_alert({message: __('Documents sent for signature'), indicator: 'green'});
                    await frm.reload_doc();
                }
            } finally {
                dialog.enable_primary_action();
            }
        }
    });
    const wrapper = dialog.fields_dict.review.$wrapper;
    $('<p>').text(__('Recipient: {0} <{1}>', [preview.recipient_name, preview.recipient_email])).appendTo(wrapper);
    $('<p class="text-muted">').text(__('Review expires in five minutes. Open every document before sending.')).appendTo(wrapper);
    const urls = [];
    for (const document of preview.documents) {
        const bytes = Uint8Array.from(atob(document.content_base64), c => c.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], {type: 'application/pdf'}));
        urls.push(url);
        $('<a target="_blank" rel="noopener">').attr({href: url}).text(document.name).appendTo(wrapper);
        $('<iframe>').attr({src: url, title: document.name}).css({width: '100%', height: '450px', border: '1px solid var(--border-color)', marginBottom: '16px'}).appendTo(wrapper);
    }
    dialog.$wrapper.on('hidden.bs.modal', () => urls.forEach(url => URL.revokeObjectURL(url)));
    dialog.show();
};
