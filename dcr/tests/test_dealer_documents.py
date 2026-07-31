"""Regression tests for race-free dealer-document uploads."""

import unittest
from unittest.mock import MagicMock, patch


class TestSetDealerDocument(unittest.TestCase):

    @patch("dcr.api.dealer_documents.frappe")
    def test_saves_field_on_fresh_customer_document(self, mock_frappe):
        from dcr.api.dealer_documents import set_dealer_document

        customer = MagicMock()
        customer.customer_group = "Dealer"
        customer.modified = "2026-07-31 10:30:00.000000"
        mock_frappe.get_doc.return_value = customer
        mock_frappe.db.exists.return_value = "FILE-001"

        result = set_dealer_document(
            "Demo Dealer",
            "w9_copy",
            "/private/files/w9-test.txt",
        )

        mock_frappe.get_doc.assert_called_once_with("Customer", "Demo Dealer")
        customer.check_permission.assert_called_once_with("write")
        mock_frappe.db.exists.assert_called_once_with(
            "File",
            {
                "file_url": "/private/files/w9-test.txt",
                "attached_to_doctype": "Customer",
                "attached_to_name": "Demo Dealer",
                "attached_to_field": "w9_copy",
            },
        )
        customer.set.assert_called_once_with("w9_copy", "/private/files/w9-test.txt")
        customer.save.assert_called_once_with()
        self.assertEqual(result["modified"], "2026-07-31 10:30:00.000000")

    @patch("dcr.api.dealer_documents.frappe")
    def test_rejects_unknown_document_field(self, mock_frappe):
        from dcr.api.dealer_documents import set_dealer_document

        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            set_dealer_document("Demo Dealer", "customer_name", "/files/test.txt")

        mock_frappe.get_doc.assert_not_called()

    @patch("dcr.api.dealer_documents.frappe")
    def test_rejects_file_not_attached_to_requested_field(self, mock_frappe):
        from dcr.api.dealer_documents import set_dealer_document

        customer = MagicMock()
        customer.customer_group = "Dealer"
        mock_frappe.get_doc.return_value = customer
        mock_frappe.db.exists.return_value = None
        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            set_dealer_document(
                "Demo Dealer",
                "retailer_application_copy",
                "/private/files/test.txt",
            )

        customer.save.assert_not_called()
