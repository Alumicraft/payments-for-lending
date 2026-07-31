"""Tests for DCR-specific Lending safeguards."""

import unittest

from dcr.lending_rules import has_material_outstanding_principal


class TestOutstandingPrincipalRule(unittest.TestCase):
    def test_interest_only_payment_keeps_loan_open(self):
        self.assertTrue(
            has_material_outstanding_principal(
                loan_amount=100_000,
                total_principal_paid=0,
                current_principal_paid=0,
            )
        )

    def test_fully_paid_principal_can_close(self):
        self.assertFalse(
            has_material_outstanding_principal(
                loan_amount=100_000,
                total_principal_paid=99_000,
                current_principal_paid=1_000,
            )
        )

    def test_small_remainder_within_write_off_limit_can_close(self):
        self.assertFalse(
            has_material_outstanding_principal(
                loan_amount=100_000,
                total_principal_paid=99_999.5,
                write_off_amount=1,
            )
        )


class TestLoanRepaymentOverrideRegistration(unittest.TestCase):
    def test_override_is_registered_and_guards_interest_only_loans(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        hooks = (root / "dcr/hooks.py").read_text()
        override = (root / "dcr/overrides/loan_repayment.py").read_text()

        self.assertIn(
            '"Loan Repayment": "dcr.overrides.loan_repayment.CustomLoanRepayment"',
            hooks,
        )
        self.assertIn("class CustomLoanRepayment(LoanRepayment)", override)
        self.assertIn("has_material_outstanding_principal", override)
        self.assertIn("def _reopen_legacy_interest_only_loan(self):", override)
        self.assertIn("super().validate()", override)
        self.assertIn("super().on_submit()", override)
        self.assertIn("super().on_cancel()", override)
