"""Tests for AdobeSign webhook signature verification.

Validates that the HMAC verification correctly accepts genuine requests
and rejects tampered ones.
"""

import hashlib
import hmac
import unittest
from unittest.mock import patch, MagicMock


class TestWebhookVerification(unittest.TestCase):

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_valid_hmac_signature_passes(self, mock_settings, mock_frappe):
        secret = "test-webhook-secret-123"
        mock_settings.return_value = {"webhook_secret": secret, "allowed_ips": ""}

        body = b'{"event":"AGREEMENT_ALL_SIGNED","agreement":{"id":"abc123"}}'
        expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        mock_request = MagicMock()
        mock_request.headers = {"X-AdobeSign-Signature": expected_sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_invalid_hmac_signature_fails(self, mock_settings, mock_frappe):
        secret = "test-webhook-secret-123"
        mock_settings.return_value = {"webhook_secret": secret, "allowed_ips": ""}

        body = b'{"event":"AGREEMENT_ALL_SIGNED"}'
        mock_request = MagicMock()
        mock_request.headers = {"X-AdobeSign-Signature": "bad-signature"}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_missing_signature_header_fails(self, mock_settings, mock_frappe):
        mock_settings.return_value = {"webhook_secret": "secret", "allowed_ips": ""}

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.get_data.return_value = b"{}"
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_no_secret_configured_rejects(self, mock_settings, mock_frappe):
        """Fail-closed: reject all requests when no webhook secret is configured."""
        mock_settings.return_value = {"webhook_secret": "", "allowed_ips": ""}

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_tampered_body_fails(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {"webhook_secret": secret, "allowed_ips": ""}

        original_body = b'{"event":"AGREEMENT_ALL_SIGNED","agreement":{"id":"abc"}}'
        sig = hmac.new(secret.encode(), original_body, hashlib.sha256).hexdigest()

        tampered_body = b'{"event":"AGREEMENT_ALL_SIGNED","agreement":{"id":"EVIL"}}'
        mock_request = MagicMock()
        mock_request.headers = {"X-AdobeSign-Signature": sig}
        mock_request.get_data.return_value = tampered_body
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())


    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_ip_whitelist_blocks_unauthorized_ip(self, mock_settings, mock_frappe):
        """Request from non-whitelisted IP is rejected before HMAC check."""
        mock_settings.return_value = {
            "webhook_secret": "secret",
            "allowed_ips": "1.2.3.4,5.6.7.8",
        }
        mock_frappe.local.request_ip = "9.9.9.9"

        from dcr.api.adobesign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_ip_whitelist_allows_authorized_ip(self, mock_settings, mock_frappe):
        """Request from whitelisted IP proceeds to HMAC check."""
        secret = "test-secret"
        mock_settings.return_value = {
            "webhook_secret": secret,
            "allowed_ips": "1.2.3.4,5.6.7.8",
        }
        mock_frappe.local.request_ip = "1.2.3.4"

        body = b'{"event":"test"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        mock_request = MagicMock()
        mock_request.headers = {"X-AdobeSign-Signature": sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.adobesign.frappe")
    @patch("dcr.api.adobesign.get_adobesign_settings")
    def test_empty_ip_whitelist_skips_check(self, mock_settings, mock_frappe):
        """Empty allowed_ips means no IP restriction."""
        secret = "test-secret"
        mock_settings.return_value = {
            "webhook_secret": secret,
            "allowed_ips": "",
        }

        body = b'{"event":"test"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        mock_request = MagicMock()
        mock_request.headers = {"X-AdobeSign-Signature": sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.adobesign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())


class TestABARoutingValidation(unittest.TestCase):
    """Tests for ABA routing number checksum validation."""

    def test_valid_routing_number_passes(self):
        """Chase routing number 021000021 is valid."""
        from dcr.api.achq_integration import _validate_routing_number
        # Should not raise
        _validate_routing_number("021000021")

    def test_valid_routing_number_2(self):
        """Bank of America 026009593 is valid."""
        from dcr.api.achq_integration import _validate_routing_number
        _validate_routing_number("026009593")

    def test_invalid_checksum_raises(self):
        """Routing number with bad checksum is rejected."""
        from dcr.api.achq_integration import _validate_routing_number
        with self.assertRaises(Exception):
            _validate_routing_number("123456789")

    def test_non_digit_raises(self):
        from dcr.api.achq_integration import _validate_routing_number
        with self.assertRaises(Exception):
            _validate_routing_number("02100002A")

    def test_wrong_length_raises(self):
        from dcr.api.achq_integration import _validate_routing_number
        with self.assertRaises(Exception):
            _validate_routing_number("12345")

    def test_valid_account_number_passes(self):
        from dcr.api.achq_integration import _validate_account_number
        _validate_account_number("12345678")

    def test_account_too_short_raises(self):
        from dcr.api.achq_integration import _validate_account_number
        with self.assertRaises(Exception):
            _validate_account_number("123")

    def test_account_too_long_raises(self):
        from dcr.api.achq_integration import _validate_account_number
        with self.assertRaises(Exception):
            _validate_account_number("123456789012345678")

    def test_account_non_digit_raises(self):
        from dcr.api.achq_integration import _validate_account_number
        with self.assertRaises(Exception):
            _validate_account_number("1234ABCD")


if __name__ == "__main__":
    unittest.main()
