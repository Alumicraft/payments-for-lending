import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


class TestPurchaseOrderEmailContext(unittest.TestCase):
    @patch("dcr.api.dcr_email.frappe")
    def test_dealer_comes_from_hbr_customer_not_factory_supplier(self, mock_frappe):
        from dcr.api.dcr_email import _purchase_order_email_context

        po = MagicMock()
        po.doctype = "Purchase Order"
        po.get.side_effect = {
            "supplier": "FACTORY-001", "supplier_name": "Factory Name",
            "custom_home_build_request": "HBR-001", "grand_total": 125000,
        }.get
        hbr = MagicMock()
        hbr.get.side_effect = {
            "customer": "DEALER-001", "home_buyer": "BUYER-001",
            "quote_no": "QUOTE-123", "financing_type": "Floored",
        }.get
        mock_frappe.get_doc.return_value = hbr
        mock_frappe.db.get_value.side_effect = lambda doctype, name, field: {
            "DEALER-001": "Dealer Name", "BUYER-001": "Buyer Name",
        }.get(name)

        result = _purchase_order_email_context(po)

        self.assertEqual(result["dealer_name"], "Dealer Name")
        self.assertEqual(result["customer_name"], "Buyer Name")
        self.assertEqual(result["quote_number"], "QUOTE-123")
        self.assertEqual(result["payment_type"], "Flooring")
        self.assertEqual(result["po_amount"], "125,000")
        hbr.check_permission.assert_called_once_with("read")
        mock_frappe.db.get_value.assert_any_call("Customer", "DEALER-001", "customer_name")

    @patch("dcr.api.dcr_email.frappe")
    def test_unreadable_linked_hbr_is_not_exposed_through_purchase_order(self, mock_frappe):
        from dcr.api.dcr_email import _purchase_order_email_context

        po = MagicMock()
        po.doctype = "Purchase Order"
        po.get.side_effect = {"custom_home_build_request": "HBR-RESTRICTED"}.get
        mock_frappe.get_doc.return_value.check_permission.side_effect = PermissionError
        with self.assertRaises(PermissionError):
            _purchase_order_email_context(po)
        mock_frappe.db.get_value.assert_not_called()

    @patch("dcr.api.dcr_email.frappe")
    def test_purchase_order_without_hbr_does_not_label_factory_as_dealer(self, mock_frappe):
        from dcr.api.dcr_email import _purchase_order_email_context

        po = MagicMock()
        po.doctype = "Purchase Order"
        po.get.side_effect = {"supplier": "FACTORY-001", "supplier_name": "Factory Name"}.get
        self.assertEqual(_purchase_order_email_context(po)["dealer_name"], "")
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.db.get_value.assert_not_called()


class TestEmailPermissions(unittest.TestCase):
    def _email_modules(self, generic):
        return {
            "emails": MagicMock(),
            "emails.email_service": MagicMock(),
            "emails.email_service.generic_email": generic,
            "emails.email_service.utils": MagicMock(),
        }

    @patch("dcr.api.dcr_email.frappe")
    def test_preview_rejects_unreadable_document_before_building_data(self, mock_frappe):
        from dcr.api.dcr_email import preview_document_email

        generic = MagicMock()
        doc = mock_frappe.get_doc.return_value
        doc.check_permission.side_effect = PermissionError
        with patch.dict("sys.modules", self._email_modules(generic)):
            with self.assertRaises(PermissionError):
                preview_document_email("Purchase Order", "PO-OTHER-DEALER")

        doc.check_permission.assert_called_once_with("read")
        generic.build_template_data.assert_not_called()
        generic.resolve_recipient_email.assert_not_called()
        generic.send_document_email.assert_not_called()

    @patch("dcr.api.dcr_email.frappe")
    def test_send_requires_read_and_email_before_calling_provider(self, mock_frappe):
        from dcr.api.dcr_email import send_purchase_order_email

        for denied_permission in ["read", "email"]:
            with self.subTest(permission=denied_permission):
                generic = MagicMock()
                doc = MagicMock()
                mock_frappe.get_doc.return_value = doc
                def check_permission(permission):
                    if permission == denied_permission:
                        raise PermissionError
                doc.check_permission.side_effect = check_permission
                with patch.dict("sys.modules", self._email_modules(generic)):
                    with self.assertRaises(PermissionError):
                        send_purchase_order_email("PO-001", "test@example.test")
                generic.send_document_email.assert_not_called()

    @patch("dcr.api.dcr_email._purchase_order_email_context", return_value={"dealer_name": "Dealer Name"})
    @patch("dcr.api.dcr_email.frappe")
    def test_authorized_send_uses_dealer_name_in_subject(self, mock_frappe, mock_context):
        from dcr.api.dcr_email import send_purchase_order_email

        generic = MagicMock()
        with patch.dict("sys.modules", self._email_modules(generic)):
            send_purchase_order_email("PO-001", "test@example.test")
        self.assertEqual(generic.send_document_email.call_args.kwargs["subject_override"],
                         "Purchase Order PO-001 — Dealer Name")
        self.assertEqual(mock_frappe.get_doc.return_value.check_permission.call_count, 2)


class TestDcrEmailFormatting(unittest.TestCase):
    def test_disbursement_email_formats_amount_before_sending(self):
        email_api = (ROOT / "dcr/api/dcr_email.py").read_text()

        self.assertIn("def _format_currency_amount", email_api)
        self.assertIn("formatted_amount = _format_currency_amount(amount)", email_api)
        self.assertIn('subject=f"Loan Advance Disbursed — ${formatted_amount}"', email_api)
        self.assertIn('"amount": formatted_amount', email_api)

    def test_email_preview_reuses_email_app_template_data_without_send(self):
        email_api = (ROOT / "dcr/api/dcr_email.py").read_text()

        self.assertIn("def preview_document_email", email_api)
        self.assertIn("build_template_data", email_api)
        self.assertIn("_build_email_preview", email_api)
        self.assertIn("PDF attachment", email_api)
        self.assertIn("def _purchase_order_email_context", email_api)
        self.assertIn("def send_purchase_order_email", email_api)
        self.assertIn('template_override="purchase-order"', email_api)
        for field in ["quote_number", "serial_number", "payment_type", "po_amount"]:
            self.assertIn(f'"{field}"', email_api)

    def test_dealer_welcome_includes_the_portal_link_in_shared_email_data(self):
        email_api = (ROOT / "dcr/api/dcr_email.py").read_text()

        self.assertIn('template="dealer-welcome"', email_api)
        self.assertIn('"portal_url": frappe.utils.get_url("/portal")', email_api)


if __name__ == "__main__":
    unittest.main()
