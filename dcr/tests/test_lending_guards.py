"""Regression tests for Lending workflow guards."""

import unittest
from unittest.mock import MagicMock, patch


class _Doc:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        setattr(self, key, value)


class TestLoanApplicationGuards(unittest.TestCase):

    @patch("dcr.api.lending.validate_advance_date")
    @patch("dcr.api.lending.get_dealer_outstanding_balance")
    @patch("dcr.api.lending.is_dealer_current")
    @patch("dcr.api.lending.frappe")
    def test_cash_hbr_cannot_back_a_loan_application(
        self, mock_frappe, mock_current, mock_outstanding, mock_advance
    ):
        from dcr.api.lending import validate_loan_application

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Cash"
            if doctype == "MIFA":
                return None
            return None

        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.throw.side_effect = Exception("Loan Application requires Floored HBR")
        mock_current.return_value = "Yes"
        mock_outstanding.return_value = 0

        doc = _Doc(
            home_build_request="HBR-CASH",
            applicant="CUST-001",
            loan_amount=100000,
            advance_date_requested=None,
            rate_of_interest=0,
            repayment_periods=0,
            custom_projected_sales_price=0,
        )

        with self.assertRaises(Exception):
            validate_loan_application(doc, "validate")


if __name__ == "__main__":
    unittest.main()
