"""Tests for ACH Transaction retry logic.

Wrong return-code routing = missed revenue or harassing closed accounts.
Tests the should_retry() decision tree without needing a database.
"""

import unittest
from unittest.mock import MagicMock

from dcr.dcr.doctype.ach_transaction.ach_transaction import (
    ACHTransaction,
    RETRYABLE_RETURN_CODES,
    NON_RETRYABLE_RETURN_CODES,
    ACHQ_REJECTION_CODES,
)


def make_txn(retry_attempt=0, max_retries=2):
    """Create a mock ACHTransaction with the fields should_retry reads."""
    txn = MagicMock(spec=ACHTransaction)
    txn.retry_attempt = retry_attempt
    txn.max_retries = max_retries
    # Bind the real method to the mock
    txn.should_retry = ACHTransaction.should_retry.__get__(txn)
    return txn


class TestShouldRetry(unittest.TestCase):

    # ------------------------------------------------------------------
    # Retryable codes (funding issues) — should retry
    # ------------------------------------------------------------------

    def test_r01_insufficient_funds_retries(self):
        txn = make_txn()
        self.assertTrue(txn.should_retry("R01"))

    def test_r09_uncollected_funds_retries(self):
        txn = make_txn()
        self.assertTrue(txn.should_retry("R09"))

    # ------------------------------------------------------------------
    # Non-retryable codes (account/auth issues) — should NOT retry
    # ------------------------------------------------------------------

    def test_r02_account_closed_no_retry(self):
        txn = make_txn()
        self.assertFalse(txn.should_retry("R02"))

    def test_r03_no_account_no_retry(self):
        txn = make_txn()
        self.assertFalse(txn.should_retry("R03"))

    def test_r07_authorization_revoked_no_retry(self):
        txn = make_txn()
        self.assertFalse(txn.should_retry("R07"))

    def test_r10_unauthorized_no_retry(self):
        txn = make_txn()
        self.assertFalse(txn.should_retry("R10"))

    def test_r29_corporate_not_authorized_no_retry(self):
        txn = make_txn()
        self.assertFalse(txn.should_retry("R29"))

    def test_all_non_retryable_codes_blocked(self):
        txn = make_txn()
        for code in NON_RETRYABLE_RETURN_CODES:
            self.assertFalse(
                txn.should_retry(code),
                f"Code {code} should NOT be retryable"
            )

    # ------------------------------------------------------------------
    # ACHQ pre-flight rejections — should NOT retry
    # ------------------------------------------------------------------

    def test_d01_duplicate_no_retry(self):
        txn = make_txn()
        self.assertFalse(txn.should_retry("D01"))

    def test_all_achq_rejection_codes_blocked(self):
        txn = make_txn()
        for code in ACHQ_REJECTION_CODES:
            self.assertFalse(
                txn.should_retry(code),
                f"ACHQ rejection code {code} should NOT be retryable"
            )

    # ------------------------------------------------------------------
    # Max retries reached — should NOT retry even for retryable codes
    # ------------------------------------------------------------------

    def test_max_retries_reached_blocks_retry(self):
        txn = make_txn(retry_attempt=2, max_retries=2)
        self.assertFalse(txn.should_retry("R01"))

    def test_max_retries_exceeded_blocks_retry(self):
        txn = make_txn(retry_attempt=3, max_retries=2)
        self.assertFalse(txn.should_retry("R01"))

    # ------------------------------------------------------------------
    # Unknown codes — default to retry (conservative)
    # ------------------------------------------------------------------

    def test_unknown_code_defaults_to_retry(self):
        txn = make_txn()
        self.assertTrue(txn.should_retry("R99"))

    def test_none_code_defaults_to_retry(self):
        txn = make_txn()
        self.assertTrue(txn.should_retry(None))

    # ------------------------------------------------------------------
    # Boundary: first attempt vs last attempt
    # ------------------------------------------------------------------

    def test_first_attempt_can_retry(self):
        txn = make_txn(retry_attempt=0, max_retries=2)
        self.assertTrue(txn.should_retry("R01"))

    def test_second_attempt_last_chance(self):
        txn = make_txn(retry_attempt=1, max_retries=2)
        self.assertTrue(txn.should_retry("R01"))


if __name__ == "__main__":
    unittest.main()
