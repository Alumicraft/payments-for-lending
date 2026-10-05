"""Review PDFs and recipients without sending; bind final send to that review."""
from unittest.mock import MagicMock, patch
import base64
import pytest
from dcr.api import docusign


@pytest.fixture
def context():
    return dict(document_type='MIFA', reference_doctype='MIFA', reference_name='MIFA-1',
        customer='DEALER-1', recipient_email='review@example.test', recipient_name='Dealer',
        fingerprint='VERSION-1', prints=[('MIFA', 'MIFA-1', 'MIFA', 'MIFA.pdf')])


def test_preview_renders_pdf_without_creating_envelope(context):
    with patch.object(docusign, '_signature_context', return_value=context), patch.object(docusign, 'frappe') as f, patch.object(docusign, 'DocuSignClient') as provider:
        f.session.user = 'staff@example.test'; f.get_print.return_value = b'%PDF-REVIEW'
        result = docusign.preview_signature('MIFA', 'MIFA-1')
        assert base64.b64decode(result['documents'][0]['content_base64']) == b'%PDF-REVIEW'
        assert result['recipient_email'] == 'review@example.test'
        provider.assert_not_called()
        f.cache.set_value.assert_called_once()


@pytest.mark.parametrize('review', [None, {'user':'other@example.test'}, {'user':'staff@example.test','document_type':'MIFA','reference_name':'OTHER'}])
def test_send_rejects_absent_expired_or_other_user_review(context, review):
    with patch.object(docusign, '_signature_context', return_value=context), patch.object(docusign, 'require_staff'), patch.object(docusign, 'frappe') as f, patch.object(docusign, 'DocuSignClient') as provider:
        f.session.user = 'staff@example.test'; f.cache.get_value.return_value = review; f.throw.side_effect = ValueError
        with pytest.raises(ValueError): docusign.send_mifa_for_signature('MIFA-1', 'TOKEN')
        provider.assert_not_called()


def test_changed_source_requires_fresh_preview(context):
    review = dict(context, user='staff@example.test', fingerprint='OLD')
    with patch.object(docusign, '_signature_context', return_value=context), patch.object(docusign, 'require_staff'), patch.object(docusign, 'frappe') as f, patch.object(docusign, 'DocuSignClient') as provider:
        f.session.user = 'staff@example.test'; f.cache.get_value.return_value = review; f.throw.side_effect = ValueError
        with pytest.raises(ValueError): docusign.send_mifa_for_signature('MIFA-1', 'TOKEN')
        provider.assert_not_called()


def test_send_uses_reviewed_bytes_and_admits_before_provider_call(context):
    review = dict(context, user='staff@example.test', documents=[{'name':'MIFA.pdf','content_base64':base64.b64encode(b'%PDF-REVIEWED').decode()}])
    with patch.object(docusign, '_signature_context', return_value=context), patch.object(docusign, 'require_staff'), patch.object(docusign, '_send_signing_email') as email, patch.object(docusign, 'frappe') as f, patch.object(docusign, 'DocuSignClient') as provider:
        f.session.user = 'staff@example.test'; f.cache.get_value.return_value = review; f.db.exists.return_value = None
        sig = f.new_doc.return_value; sig.name = 'SIG-1'
        def send(**kw):
            assert sig.status == 'Outcome Unknown'
            f.db.commit.assert_called_once()
            assert kw['documents'][0]['content'] == b'%PDF-REVIEWED'
            assert kw['transaction_id'] == 'SIG-1'
            return {'envelope_id':'ENV-1'}
        provider.return_value.create_envelope.side_effect = send
        result = docusign.send_mifa_for_signature('MIFA-1', 'TOKEN')
        assert result['success']; assert sig.status == 'Sent'
        f.get_print.assert_not_called()
        email.assert_called_once()


def test_unknown_envelope_result_blocks_duplicate_send(context):
    review = dict(context, user='staff@example.test', documents=[])
    with patch.object(docusign, '_signature_context', return_value=context), patch.object(docusign, 'require_staff'), patch.object(docusign, '_send_signing_email') as email, patch.object(docusign, 'frappe') as f, patch.object(docusign, 'DocuSignClient') as provider:
        f.session.user = 'staff@example.test'; f.cache.get_value.return_value = review; f.db.exists.return_value = None
        provider.return_value.create_envelope.side_effect = TimeoutError
        with pytest.raises(TimeoutError): docusign.send_mifa_for_signature('MIFA-1', 'TOKEN')
        assert f.new_doc.return_value.status == 'Outcome Unknown'
        f.db.commit.assert_called_once()
        email.assert_not_called()


def test_signing_link_uses_reviewed_recipient_after_customer_edit():
    record = MagicMock(); record.status='Sent'; record.customer='DEALER-1'; record.document_type='MIFA'; record.envelope_id='ENV-1'
    record.get.side_effect={'recipient_email':'reviewed@example.test','recipient_name':'Reviewed Dealer'}.get
    with patch.object(docusign,'_verify_signing_token',return_value=True), patch.object(docusign,'frappe') as f, patch.object(docusign,'DocuSignClient') as provider:
        f.db.get_value.return_value=record
        f.get_doc.return_value.email_id='new@example.test'
        docusign.sign_document('SIG-1','TOKEN')
        args=provider.return_value.get_signing_url.call_args.kwargs
        assert args['email']=='reviewed@example.test'
        assert args['name']=='Reviewed Dealer'


@pytest.mark.parametrize('payload', [
    {'envelopeId':'ENV-1','status':'completed'},
    {'event':'envelope-completed','data':{'envelopeId':'ENV-1'}},
    {'data':{'envelopeId':'ENV-1','envelopeSummary':{'status':'completed'}}},
])
def test_connect_callback_accepts_actual_json_sim_payload(payload):
    import json
    with patch.object(docusign,'_verify_webhook_request',return_value=True), patch.object(docusign,'_handle_envelope_completed') as complete, patch.object(docusign,'frappe') as f:
        f.request.get_data.return_value=json.dumps(payload)
        assert docusign.docusign_webhook()=={'status':'success'}
        complete.assert_called_once_with('ENV-1',payload)


def test_duplicate_completion_does_not_download_or_notify_again():
    with patch.object(docusign,'frappe') as f, patch.object(docusign,'DocuSignClient') as provider, patch.object(docusign,'_update_reference_document') as update:
        f.db.get_value.side_effect=['SIG-1','SIG-1']
        doc=f.get_doc.return_value; doc.status='Signed'; doc.signed_attachment='/private/files/signed.pdf'
        docusign._handle_envelope_completed('ENV-1',{})
        provider.assert_not_called(); update.assert_not_called()


def test_pdf_failure_does_not_mark_document_signed():
    with patch.object(docusign,'frappe') as f, patch.object(docusign,'DocuSignClient') as provider:
        f.db.get_value.side_effect=['SIG-1','SIG-1']; f.get_doc.return_value.status='Sent'
        provider.return_value.get_envelope_document.side_effect=TimeoutError
        with pytest.raises(TimeoutError): docusign._handle_envelope_completed('ENV-1',{})
        f.db.set_value.assert_not_called()


def test_connect_failure_returns_retryable_error_and_rolls_back():
    with patch.object(docusign,'_verify_webhook_request',return_value=True), patch.object(docusign,'_handle_envelope_completed',side_effect=TimeoutError), patch.object(docusign,'frappe') as f:
        f.local.response={}; f.request.get_data.return_value='{"event":"envelope-completed","data":{"envelopeId":"ENV-1"}}'
        assert docusign.docusign_webhook()['status']=='error'
        assert f.local.response['http_status_code']==500
        f.db.rollback.assert_called_once()


@pytest.mark.parametrize('status',['Declined','Voided'])
def test_late_decline_or_void_does_not_regress_signed_envelope(status):
    with patch.object(docusign,'frappe') as f:
        f.db.get_value.side_effect=['SIG-1','Signed']
        docusign._handle_envelope_declined('ENV-1',{},status)
        f.db.set_value.assert_not_called()


def test_voided_json_sim_event_releases_sent_request():
    with patch.object(docusign,'_verify_webhook_request',return_value=True), patch.object(docusign,'_handle_envelope_declined') as void, patch.object(docusign,'frappe') as f:
        f.request.get_data.return_value='{"event":"envelope-voided","data":{"envelopeId":"ENV-1"}}'
        docusign.docusign_webhook()
        assert void.call_args.args[0]=='ENV-1'
        assert void.call_args.args[2]=='Voided'
