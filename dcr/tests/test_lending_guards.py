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

    @patch("dcr.api.lending.validate_advance_date")
    @patch("dcr.api.lending.get_dealer_outstanding_balance")
    @patch("dcr.api.lending.is_dealer_current")
    @patch("dcr.api.lending.frappe")
    def test_loan_application_validate_backfills_hbr_values(
        self, mock_frappe, mock_current, mock_outstanding, mock_advance
    ):
        from dcr.api.lending import validate_loan_application

        hbr = _Doc(
            customer="CUST-001",
            home_invoice_plus_freight=215000,
            home_buyer="BUYER-001",
            home_serial_no="SER-001",
            factory="Factory A",
            model_name="Model A",
            space_rent=123,
            selling_price=250000,
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Floored"
            if doctype == "Customer" and fieldname == ["email_id", "mobile_no", "phone"]:
                return {
                    "email_id": "dealer@example.test",
                    "mobile_no": "555-111-2222",
                    "phone": None,
                }
            if doctype == "MIFA":
                return None
            return None

        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.get_doc.return_value = hbr
        mock_current.return_value = "Yes"
        mock_outstanding.return_value = 0

        doc = _Doc(
            home_build_request="HBR-FLOORED",
            applicant_type=None,
            applicant=None,
            loan_amount=None,
            requested_advance_amount=None,
            custom_quote_amount=None,
            buyer_name=None,
            home_serial_no=None,
            factory=None,
            floor_plan=None,
            custom_monthly_space_rent=None,
            custom_projected_sales_price=None,
            applicant_email_address=None,
            applicant_phone_number=None,
            loan_product=None,
            advance_date_requested=None,
            rate_of_interest=0,
            repayment_periods=0,
            custom_projected_equity=None,
            custom_projected_ltv=None,
        )

        validate_loan_application(doc, "validate")

        self.assertEqual(doc.applicant_type, "Customer")
        self.assertEqual(doc.applicant, "CUST-001")
        self.assertEqual(doc.loan_amount, 215000)
        self.assertEqual(doc.requested_advance_amount, 215000)
        self.assertEqual(doc.custom_quote_amount, 215000)
        self.assertEqual(doc.buyer_name, "BUYER-001")
        self.assertEqual(doc.home_serial_no, "SER-001")
        self.assertEqual(doc.factory, "Factory A")
        self.assertEqual(doc.floor_plan, "Model A")
        self.assertEqual(doc.custom_monthly_space_rent, 123)
        self.assertEqual(doc.custom_projected_sales_price, 250000)
        self.assertEqual(doc.applicant_email_address, "dealer@example.test")
        self.assertEqual(doc.applicant_phone_number, "555-111-2222")

    @patch("dcr.api.lending.validate_advance_date")
    @patch("dcr.api.lending.get_dealer_outstanding_balance")
    @patch("dcr.api.lending.is_dealer_current")
    @patch("dcr.api.lending.frappe")
    def test_loan_application_contact_backfill_uses_linked_contact(
        self, mock_frappe, mock_current, mock_outstanding, mock_advance
    ):
        from dcr.api.lending import validate_loan_application

        hbr = _Doc(
            customer="CUST-001",
            home_invoice_plus_freight=215000,
            home_buyer=None,
            home_serial_no=None,
            factory=None,
            model_name=None,
            space_rent=None,
            selling_price=None,
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Floored"
            if doctype == "Customer" and fieldname == ["email_id", "mobile_no", "phone"]:
                return {"email_id": None, "mobile_no": None, "phone": None}
            if doctype == "Dynamic Link":
                return "CONT-001"
            if doctype == "Contact" and fieldname == ["email_id", "mobile_no", "phone"]:
                return {
                    "email_id": "linked-contact@example.test",
                    "mobile_no": None,
                    "phone": "555-333-4444",
                }
            if doctype == "MIFA":
                return None
            return None

        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.get_doc.return_value = hbr
        mock_current.return_value = "Yes"
        mock_outstanding.return_value = 0

        doc = _Doc(
            home_build_request="HBR-FLOORED",
            applicant_type=None,
            applicant=None,
            loan_amount=None,
            requested_advance_amount=None,
            custom_quote_amount=None,
            buyer_name=None,
            home_serial_no=None,
            factory=None,
            floor_plan=None,
            custom_monthly_space_rent=None,
            custom_projected_sales_price=None,
            applicant_email_address=None,
            applicant_phone_number=None,
            loan_product=None,
            advance_date_requested=None,
            rate_of_interest=0,
            repayment_periods=0,
            custom_projected_equity=None,
            custom_projected_ltv=None,
        )

        validate_loan_application(doc, "validate")

        self.assertEqual(doc.applicant_email_address, "linked-contact@example.test")
        self.assertEqual(doc.applicant_phone_number, "555-333-4444")


if __name__ == "__main__":
    unittest.main()
