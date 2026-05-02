"""Tests for repayment schedule logic.

get_next_unpaid_repayment() reads the Frappe Lending repayment schedule
and cross-references Loan Repayment records to find the next due payment.
Must match Frappe Lending v15 schema exactly.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import date


class TestGetNextUnpaidRepayment(unittest.TestCase):

    @patch("dcr.tasks.scheduled_debits.frappe")
    @patch("dcr.tasks.scheduled_debits.today")
    def test_returns_first_unpaid_future_row(self, mock_today, mock_frappe):
        mock_today.return_value = "2025-03-01"

        from dcr.tasks.scheduled_debits import get_next_unpaid_repayment

        # No repayments made yet
        mock_frappe.get_all.return_value = []

        loan = MagicMock()
        loan.name = "LOAN-001"
        loan.repayment_schedule = [
            MagicMock(payment_date="2025-02-01", total_payment=1000),  # past
            MagicMock(payment_date="2025-03-01", total_payment=1000),  # today
            MagicMock(payment_date="2025-04-01", total_payment=1000),  # future
        ]

        payment_date, amount = get_next_unpaid_repayment(loan)
        self.assertEqual(payment_date, date(2025, 3, 1))
        self.assertEqual(amount, 1000)

    @patch("dcr.tasks.scheduled_debits.frappe")
    @patch("dcr.tasks.scheduled_debits.today")
    def test_skips_already_paid_dates(self, mock_today, mock_frappe):
        mock_today.return_value = "2025-03-01"

        from dcr.tasks.scheduled_debits import get_next_unpaid_repayment

        # March payment already made (pluck returns flat list of dates)
        mock_frappe.get_all.return_value = ["2025-03-01"]

        loan = MagicMock()
        loan.name = "LOAN-001"
        loan.repayment_schedule = [
            MagicMock(payment_date="2025-03-01", total_payment=1000),
            MagicMock(payment_date="2025-04-01", total_payment=1000),
        ]

        payment_date, amount = get_next_unpaid_repayment(loan)
        self.assertEqual(payment_date, date(2025, 4, 1))
        self.assertEqual(amount, 1000)

    @patch("dcr.tasks.scheduled_debits.frappe")
    @patch("dcr.tasks.scheduled_debits.today")
    def test_all_paid_returns_none(self, mock_today, mock_frappe):
        mock_today.return_value = "2025-03-01"

        from dcr.tasks.scheduled_debits import get_next_unpaid_repayment

        mock_frappe.get_all.return_value = ["2025-03-01", "2025-04-01"]

        loan = MagicMock()
        loan.name = "LOAN-001"
        loan.repayment_schedule = [
            MagicMock(payment_date="2025-03-01", total_payment=1000),
            MagicMock(payment_date="2025-04-01", total_payment=1000),
        ]

        payment_date, amount = get_next_unpaid_repayment(loan)
        self.assertIsNone(payment_date)
        self.assertIsNone(amount)

    @patch("dcr.tasks.scheduled_debits.frappe")
    @patch("dcr.tasks.scheduled_debits.today")
    def test_empty_schedule_returns_none(self, mock_today, mock_frappe):
        mock_today.return_value = "2025-03-01"

        from dcr.tasks.scheduled_debits import get_next_unpaid_repayment

        loan = MagicMock()
        loan.name = "LOAN-001"
        loan.repayment_schedule = []

        payment_date, amount = get_next_unpaid_repayment(loan)
        self.assertIsNone(payment_date)
        self.assertIsNone(amount)

    @patch("dcr.tasks.scheduled_debits.frappe")
    @patch("dcr.tasks.scheduled_debits.today")
    def test_no_schedule_attribute_returns_none(self, mock_today, mock_frappe):
        mock_today.return_value = "2025-03-01"

        from dcr.tasks.scheduled_debits import get_next_unpaid_repayment

        loan = MagicMock(spec=[])  # no repayment_schedule attr
        loan.name = "LOAN-001"

        payment_date, amount = get_next_unpaid_repayment(loan)
        self.assertIsNone(payment_date)
        self.assertIsNone(amount)

    @patch("dcr.tasks.scheduled_debits.frappe")
    @patch("dcr.tasks.scheduled_debits.today")
    def test_uses_total_payment_not_monthly_repayment(self, mock_today, mock_frappe):
        """Frappe Lending v15 uses row.total_payment, not monthly_repayment_amount."""
        mock_today.return_value = "2025-06-01"

        from dcr.tasks.scheduled_debits import get_next_unpaid_repayment

        mock_frappe.get_all.return_value = []

        loan = MagicMock()
        loan.name = "LOAN-001"
        row = MagicMock(payment_date="2025-06-15", total_payment=2500)
        # Ensure there is no monthly_repayment_amount — only total_payment
        del row.monthly_repayment_amount
        loan.repayment_schedule = [row]

        payment_date, amount = get_next_unpaid_repayment(loan)
        self.assertEqual(amount, 2500)


class TestProcessUpcomingPayments(unittest.TestCase):

    @patch("dcr.tasks.scheduled_debits.process_loan_payment")
    @patch("dcr.tasks.scheduled_debits.is_ach_enabled")
    @patch("dcr.tasks.scheduled_debits.frappe")
    def test_includes_active_loans(self, mock_frappe, mock_is_enabled, mock_process):
        """Active loans must be swept for upcoming ACH payments."""
        from dcr.tasks.scheduled_debits import process_upcoming_payments

        mock_is_enabled.return_value = True
        settings = MagicMock()
        settings.advance_notification_days = 5
        settings.days_before_due_to_initiate = 3
        mock_frappe.get_single.return_value = settings
        mock_frappe.get_all.return_value = []

        process_upcoming_payments()

        filters = mock_frappe.get_all.call_args.kwargs["filters"]
        self.assertIn("Active", filters["status"][1])


if __name__ == "__main__":
    unittest.main()
