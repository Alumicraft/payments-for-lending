"""A browser return event cannot stand in for provider-confirmed completion."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dcr.api import docusign
from dcr.www import docusign_complete


@pytest.mark.parametrize('event',[None,'signing_complete','cancel'])
def test_unsigned_email_return_does_not_claim_signed(event):
    with patch.object(docusign,'frappe') as f, patch.object(docusign,'_verify_signing_token',return_value=True), \
         patch.object(docusign,'DocuSignClient') as client, patch.object(docusign,'_handle_envelope_completed') as completed:
        f.db.get_value.return_value = {'envelope_id':'TEST-ENVELOPE','status':'Sent'}
        f.local.response = {}
        f.utils.get_url.side_effect = lambda path:path
        client.return_value.get_envelope_status.return_value = 'sent'
        docusign.signing_complete('SIG-TEST','test-token',event=event)
        assert f.local.response['location'] == '/docusign-complete?event=pending'
        completed.assert_not_called()
        f.db.commit.assert_not_called()


def test_provider_failure_returns_pending_without_claiming_signed():
    with patch.object(docusign,'frappe') as f, patch.object(docusign,'_verify_signing_token',return_value=True), \
         patch.object(docusign,'DocuSignClient') as client:
        f.db.get_value.return_value = {'envelope_id':'TEST-ENVELOPE','status':'Sent'}
        f.local.response = {}
        f.utils.get_url.side_effect = lambda path:path
        client.return_value.get_envelope_status.side_effect = TimeoutError('Provider unavailable')
        docusign.signing_complete('SIG-TEST','test-token',event='signing_complete')
        assert f.local.response['location'] == '/docusign-complete?event=pending'


@pytest.mark.parametrize('event',['pending','unknown',''])
def test_unconfirmed_landing_page_never_says_signed(event):
    context = SimpleNamespace()
    with patch.object(docusign_complete,'frappe') as f:
        f.form_dict = {'event':event}
        docusign_complete.get_context(context)
    assert context.title == 'Signature not confirmed'
    assert 'successfully' not in context.message
