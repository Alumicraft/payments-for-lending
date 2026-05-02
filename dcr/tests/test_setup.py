"""Tests for setup helpers that provision DCR custom fields."""

import unittest
from unittest.mock import MagicMock, patch


class TestSetupCustomFields(unittest.TestCase):

    @patch("dcr.setup.frappe")
    def test_ensure_purchase_order_hbr_field_creates_missing_field(self, mock_frappe):
        from dcr.setup import ensure_purchase_order_hbr_field

        field_doc = MagicMock()
        mock_frappe.db.exists.return_value = False
        mock_frappe.get_doc.return_value = field_doc

        ensure_purchase_order_hbr_field()

        payload = mock_frappe.get_doc.call_args.args[0]
        self.assertEqual(payload["doctype"], "Custom Field")
        self.assertEqual(payload["dt"], "Purchase Order")
        self.assertEqual(payload["fieldname"], "custom_home_build_request")
        self.assertEqual(payload["options"], "Home Build Request")
        field_doc.insert.assert_called_once_with(ignore_permissions=True)
        mock_frappe.clear_cache.assert_called_once_with(doctype="Purchase Order")


if __name__ == "__main__":
    unittest.main()
