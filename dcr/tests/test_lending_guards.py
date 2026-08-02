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

    def items(self):
        return self.__dict__.items()


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
            name="HBR-FLOORED",
            customer="CUST-001",
            home_invoice_plus_freight=215000,
            home_buyer="BUYER-001",
            home_serial_no="SER-001",
            factory="Factory A",
            floor_plan="Model A",
            space_rent=123,
            selling_price=250000,
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Floored"
            if doctype == "Customer" and fieldname == ["email_id", "mobile_no"]:
                return {
                    "email_id": "dealer@example.test",
                    "mobile_no": "555-111-2222",
                }
            if doctype == "Customer" and fieldname == "customer_primary_address":
                return "CUST-001-Billing"
            if doctype == "Address":
                return {
                    "address_line1": "41888 Arbor Glen",
                    "address_line2": None,
                    "city": "Temecula",
                    "state": "CA",
                    "pincode": "92592",
                    "country": "United States",
                }
            if doctype == "Customer" and fieldname == "default_loan_product":
                return "Dealer Floor Plan"
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
            address_line_1=None,
            address_line_2=None,
            city=None,
            state=None,
            zip_code=None,
            country=None,
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
        self.assertEqual(doc.address_line_1, "41888 Arbor Glen")
        self.assertEqual(doc.city, "Temecula")
        self.assertEqual(doc.state, "CA")
        self.assertEqual(doc.zip_code, "92592")
        self.assertEqual(doc.country, "United States")
        self.assertEqual(doc.loan_product, "Dealer Floor Plan")

    @patch("dcr.api.lending.frappe")
    def test_loan_application_defaults_endpoint_returns_client_mandatory_fields(
        self, mock_frappe
    ):
        from dcr.api.lending import get_loan_application_defaults

        hbr = _Doc(
            name="HBR-FLOORED",
            customer="CUST-001",
            home_invoice_plus_freight=215000,
            home_buyer="BUYER-001",
            home_serial_no="SER-001",
            factory="Factory A",
            floor_plan="Model A",
            space_rent=123,
            selling_price=250000,
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Floored"
            if doctype == "Customer" and fieldname == ["email_id", "mobile_no"]:
                return {
                    "email_id": "dealer@example.test",
                    "mobile_no": "555-111-2222",
                }
            if doctype == "Customer" and fieldname == "default_loan_product":
                return "Dealer Floor Plan"
            if doctype == "Customer" and fieldname == "customer_primary_address":
                return "CUST-001-Billing"
            if doctype == "Address":
                return {
                    "address_line1": "41888 Arbor Glen",
                    "address_line2": None,
                    "city": "Temecula",
                    "state": "CA",
                    "pincode": "92592",
                    "country": "United States",
                }
            return None

        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.get_doc.return_value = hbr

        defaults = get_loan_application_defaults("HBR-FLOORED")

        self.assertEqual(defaults["applicant_type"], "Customer")
        self.assertEqual(defaults["home_build_request"], "HBR-FLOORED")
        self.assertEqual(defaults["applicant"], "CUST-001")
        self.assertEqual(defaults["loan_amount"], 215000)
        self.assertEqual(defaults["applicant_email_address"], "dealer@example.test")
        self.assertEqual(defaults["applicant_phone_number"], "555-111-2222")
        self.assertEqual(defaults["loan_product"], "Dealer Floor Plan")
        self.assertEqual(defaults["address_line_1"], "41888 Arbor Glen")

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
            floor_plan=None,
            space_rent=None,
            selling_price=None,
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Home Build Request" and fieldname == "docstatus":
                return 1
            if doctype == "Home Build Request" and fieldname == "financing_type":
                return "Floored"
            if doctype == "Customer" and fieldname == ["email_id", "mobile_no"]:
                return {"email_id": None, "mobile_no": None}
            if doctype == "Dynamic Link":
                return "CONT-001"
            if doctype == "Contact" and fieldname == ["email_id", "mobile_no"]:
                return {
                    "email_id": "linked-contact@example.test",
                    "mobile_no": "555-333-4444",
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


class TestLoanDefaults(unittest.TestCase):

    @patch("dcr.api.lending.frappe")
    def test_loan_defaults_endpoint_returns_application_and_deal_fields(
        self, mock_frappe
    ):
        from dcr.api.lending import get_loan_defaults_from_application

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Loan Application":
                return _Doc(
                    docstatus=1,
                    applicant="CUST-001",
                    loan_product="Standard",
                    loan_amount=25000,
                    rate_of_interest=12,
                    repayment_method="Repay Over Number of Periods",
                    repayment_periods=12,
                    home_build_request="ACC-HBR-2026-00011",
                    home_serial_no="E2E-20260525-001",
                    buyer_name=None,
                    factory="Champion Home Builders",
                )
            if doctype == "Factory Assignment":
                return 2.5
            return None

        mock_frappe.db.get_value.side_effect = get_value

        defaults = get_loan_defaults_from_application("ACC-LOAP-2026-00007")

        self.assertEqual(defaults["loan_application"], "ACC-LOAP-2026-00007")
        self.assertEqual(defaults["applicant"], "CUST-001")
        self.assertEqual(defaults["loan_product"], "Standard")
        self.assertEqual(defaults["loan_amount"], 25000)
        self.assertEqual(defaults["rate_of_interest"], 12)
        self.assertEqual(defaults["repayment_method"], "Repay Over Number of Periods")
        self.assertEqual(defaults["repayment_periods"], 12)
        self.assertEqual(defaults["qualifying_amount"], 25000)
        self.assertEqual(defaults["home_build_request"], "ACC-HBR-2026-00011")
        self.assertEqual(defaults["home_serial_no"], "E2E-20260525-001")
        self.assertEqual(defaults["factory"], "Champion Home Builders")
        self.assertEqual(defaults["custom_rebate_percentage"], 2.5)


class TestLoanCalculations(unittest.TestCase):
    def test_loan_calculation_uses_qualifying_amount_alias(self):
        from dcr.api.lending import _apply_loan_calculation_values

        doc = _Doc(
            loan_amount=None,
            qualifying_amount=220000,
            rate_of_interest=12,
            repayment_periods=12,
            custom_projected_sales_price=None,
        )

        _apply_loan_calculation_values(doc)

        self.assertEqual(doc.total_interest_payable, 26400)
        self.assertEqual(doc.total_payment, 246400)

    def test_loan_calculation_prefers_visible_qualifying_amount(self):
        from dcr.api.lending import _apply_loan_calculation_values

        doc = _Doc(
            doctype="Loan",
            loan_amount=220000,
            qualifying_amount=100000,
            rate_of_interest=12,
            repayment_periods=12,
            custom_projected_sales_price=None,
        )

        _apply_loan_calculation_values(doc)

        self.assertEqual(doc.total_interest_payable, 12000)
        self.assertEqual(doc.total_payment, 112000)

    @patch("dcr.api.lending._populate_deal_reference")
    def test_loan_validate_defaults_visible_amount_and_tenure(self, mock_reference):
        from dcr.api.lending import on_loan_validate

        doc = _Doc(
            doctype="Loan",
            docstatus=0,
            loan_amount=220000,
            qualifying_amount=None,
            rate_of_interest=12,
            repayment_periods=0,
            custom_projected_sales_price=None,
        )

        on_loan_validate(doc, "validate")

        self.assertEqual(doc.qualifying_amount, 220000)
        self.assertEqual(doc.repayment_periods, 12)
        self.assertEqual(doc.total_interest_payable, 26400)
        self.assertEqual(doc.total_payment, 246400)

    def test_interest_only_calculation_matches_floor_plan_schedule(self):
        from dcr.api.lending import _loan_calculation_values

        values = _loan_calculation_values(120000, 12, 10, 150000)

        self.assertEqual(values["repayment_amount"], 1200)
        self.assertEqual(values["monthly_repayment_amount"], 1200)
        self.assertEqual(values["total_payable_interest"], 12000)
        self.assertEqual(values["total_payment"], 132000)
        self.assertEqual(values["custom_projected_equity"], 30000)
        self.assertEqual(values["custom_projected_ltv"], 80)

    def test_calculation_clears_totals_when_rate_or_amount_is_missing(self):
        from dcr.api.lending import _loan_calculation_values

        values = _loan_calculation_values(120000, 0, 10, 150000)

        self.assertIsNone(values["repayment_amount"])
        self.assertIsNone(values["total_interest_payable"])
        self.assertEqual(values["custom_projected_equity"], 30000)

    @patch("dcr.api.lending.frappe")
    def test_loan_defaults_infers_hbr_for_older_application_without_link(
        self, mock_frappe
    ):
        from dcr.api.lending import get_loan_defaults_from_application

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Loan Application":
                return _Doc(
                    docstatus=1,
                    applicant="CUST-001",
                    loan_product="Standard",
                    loan_amount=25000,
                    rate_of_interest=12,
                    repayment_method="Repay Over Number of Periods",
                    repayment_periods=12,
                    home_build_request=None,
                    home_serial_no="E2E-20260525-001",
                    buyer_name=None,
                    factory="Champion Home Builders",
                )
            if doctype == "Home Build Request":
                self.assertEqual(
                    name_or_filters,
                    {
                        "home_serial_no": "E2E-20260525-001",
                        "docstatus": 1,
                        "customer": "CUST-001",
                        "factory": "Champion Home Builders",
                    },
                )
                return "ACC-HBR-2026-00011"
            return None

        mock_frappe.db.get_value.side_effect = get_value

        defaults = get_loan_defaults_from_application("ACC-LOAP-2026-00007")

        self.assertEqual(defaults["home_build_request"], "ACC-HBR-2026-00011")


if __name__ == "__main__":
    unittest.main()
