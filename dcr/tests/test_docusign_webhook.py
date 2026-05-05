"""Tests for DocuSign webhook signature verification.

Validates that the HMAC verification correctly accepts genuine requests
and rejects tampered ones. DocuSign uses base64-encoded HMAC-SHA256
in the X-DocuSign-Signature-1 header.
"""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import patch, MagicMock


class TestDocuSignWebhookVerification(unittest.TestCase):

    @patch("dcr.api.docusign.requests.post")
    @patch("dcr.api.docusign.DocuSignClient._headers")
    @patch("dcr.api.docusign.frappe")
    def test_envelope_notifications_request_hmac_signature(
        self, mock_frappe, mock_headers, mock_post
    ):
        """Envelope-level callbacks must include HMAC for fail-closed webhook auth."""
        settings = MagicMock()
        settings.enabled = True
        settings.account_id = "acct-123"
        settings.get_base_url.return_value = "https://demo.docusign.net/restapi"
        mock_frappe.get_single.return_value = settings
        mock_headers.return_value = {"Authorization": "Bearer token", "Content-Type": "application/json"}

        response = MagicMock()
        response.ok = True
        response.json.return_value = {"envelopeId": "env-123"}
        mock_post.return_value = response

        from dcr.api.docusign import DocuSignClient

        client = DocuSignClient()
        client.create_envelope(
            name="Flooring Packet - Test Homes 3",
            recipients=[{"email": "send2tristan@gmail.com", "name": "Test Homes 3"}],
            documents=[{"content": b"%PDF", "name": "packet.pdf"}],
            webhook_url="https://backdesk.dealercapital.net/api/method/dcr.api.docusign.docusign_webhook",
            client_user_id="Test Homes 3-Flooring Packet",
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["eventNotification"]["includeHMAC"], "true")
        self.assertEqual(payload["eventNotification"]["deliveryMode"], "SIM")
        self.assertEqual(payload["eventNotification"]["eventData"]["format"], "json")

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_valid_hmac_signature_passes(self, mock_settings, mock_frappe):
        secret = "test-webhook-secret-123"
        mock_settings.return_value = {"webhook_hmac_key": secret, "allowed_ips": ""}

        body = b'{"envelopeId":"abc123","status":"completed"}'
        expected_sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()

        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": expected_sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_invalid_hmac_signature_fails(self, mock_settings, mock_frappe):
        secret = "test-webhook-secret-123"
        mock_settings.return_value = {"webhook_hmac_key": secret, "allowed_ips": ""}

        body = b'{"envelopeId":"abc123","status":"completed"}'
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": "bad-signature"}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_missing_signature_header_fails(self, mock_settings, mock_frappe):
        mock_settings.return_value = {"webhook_hmac_key": "secret", "allowed_ips": ""}

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.get_data.return_value = b"{}"
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_no_hmac_key_configured_rejects(self, mock_settings, mock_frappe):
        """Fail-closed: reject all requests when no HMAC key is configured."""
        mock_settings.return_value = {"webhook_hmac_key": "", "allowed_ips": ""}

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_tampered_body_fails(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {"webhook_hmac_key": secret, "allowed_ips": ""}

        original_body = b'{"envelopeId":"abc","status":"completed"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), original_body, hashlib.sha256).digest()
        ).decode()

        tampered_body = b'{"envelopeId":"EVIL","status":"completed"}'
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": sig}
        mock_request.get_data.return_value = tampered_body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_ip_whitelist_blocks_unauthorized_ip(self, mock_settings, mock_frappe):
        mock_settings.return_value = {
            "webhook_hmac_key": "secret",
            "allowed_ips": "1.2.3.4,5.6.7.8",
        }
        mock_frappe.local.request_ip = "9.9.9.9"

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_ip_whitelist_allows_authorized_ip(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {
            "webhook_hmac_key": secret,
            "allowed_ips": "1.2.3.4,5.6.7.8",
        }
        mock_frappe.local.request_ip = "1.2.3.4"

        body = b'{"envelopeId":"test"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_empty_ip_whitelist_skips_check(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {
            "webhook_hmac_key": secret,
            "allowed_ips": "",
        }

        body = b'{"envelopeId":"test"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    def test_signing_return_url_keeps_signature_context(self, mock_frappe):
        mock_frappe.utils.get_url.side_effect = lambda path: f"https://backdesk.test{path}"

        from dcr.api.docusign import _get_signing_return_url

        self.assertEqual(
            _get_signing_return_url("SIG-0173", "token-123"),
            "https://backdesk.test/api/method/dcr.api.docusign.signing_complete?sig=SIG-0173&token=token-123",
        )

    @patch("dcr.api.docusign._handle_envelope_completed")
    @patch("dcr.api.docusign.DocuSignClient")
    @patch("dcr.api.docusign._verify_signing_token")
    @patch("dcr.api.docusign.frappe")
    def test_signing_complete_finalizes_completed_envelope(
        self, mock_frappe, mock_verify, mock_client_class, mock_handle
    ):
        mock_verify.return_value = True
        mock_frappe.db.get_value.return_value = {
            "envelope_id": "env-123",
            "status": "Sent",
        }
        mock_client = MagicMock()
        mock_client.get_envelope_status.return_value = "completed"
        mock_client_class.return_value = mock_client
        mock_frappe.local.response = {}
        mock_frappe.utils.get_url.side_effect = lambda path: f"https://backdesk.test{path}"

        from dcr.api.docusign import signing_complete

        signing_complete("SIG-0173", "token-123", event="signing_complete")

        mock_handle.assert_called_once_with("env-123", {"status": "completed"})
        mock_frappe.db.commit.assert_called_once()
        self.assertEqual(mock_frappe.local.response["type"], "redirect")
        self.assertEqual(
            mock_frappe.local.response["location"],
            "https://backdesk.test/docusign-complete?event=signing_complete",
        )


if __name__ == "__main__":
    unittest.main()
