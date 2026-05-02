"""Tests for guest Plaid setup URL tokens."""

import hashlib
import hmac
import unittest
from unittest.mock import patch


def _token(secret, customer, issued_at):
    sig = hmac.new(
        secret.encode(),
        f"{customer}:{issued_at}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"{issued_at}:{sig}"


class TestPlaidSetupTokens(unittest.TestCase):

    def _mock_secret(self, mock_frappe, secret="secret-key"):
        mock_frappe.local.conf.get.side_effect = (
            lambda key: secret if key in ("encryption_key", "secret_key") else None
        )

    @patch("dcr.www.plaid_setup.time", create=True)
    @patch("dcr.www.plaid_setup.frappe")
    def test_fresh_token_verifies(self, mock_frappe, mock_time):
        from dcr.www.plaid_setup import verify_plaid_token

        self._mock_secret(mock_frappe)
        mock_time.time.return_value = 1_700_000_100

        self.assertTrue(
            verify_plaid_token("CUST-001", _token("secret-key", "CUST-001", 1_700_000_000))
        )

    @patch("dcr.www.plaid_setup.time", create=True)
    @patch("dcr.www.plaid_setup.frappe")
    def test_expired_token_is_rejected(self, mock_frappe, mock_time):
        from dcr.www.plaid_setup import verify_plaid_token

        self._mock_secret(mock_frappe)
        mock_time.time.return_value = 1_700_700_000

        self.assertFalse(
            verify_plaid_token("CUST-001", _token("secret-key", "CUST-001", 1_700_000_000))
        )


if __name__ == "__main__":
    unittest.main()
