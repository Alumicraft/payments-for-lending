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


if __name__ == "__main__":
    unittest.main()
