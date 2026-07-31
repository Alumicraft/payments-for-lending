"""Tests for DCR accounting defaults."""

import unittest
from unittest.mock import MagicMock, patch


class DotDict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class TestPurchaseInvoiceDefaults(unittest.TestCase):
    def test_receipt_row_uses_company_accrual_account(self):
        from dcr.api import accounting

        doc = DotDict(
            company="Dealer Capital Resources",
            items=[
                DotDict(
                    purchase_receipt="MAT-PRE-2026-00003",
                    expense_account=None,
                )
            ],
        )
        mock_frappe = MagicMock()
        mock_frappe.db.get_value.return_value = "Stock Received But Not Billed - DCR"

        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)

        self.assertEqual(
            doc["items"][0].expense_account,
            "Stock Received But Not Billed - DCR",
        )
        mock_frappe.db.get_value.assert_called_once_with(
            "Company",
            "Dealer Capital Resources",
            "stock_received_but_not_billed",
        )

    def test_existing_expense_account_is_preserved(self):
        from dcr.api import accounting

        doc = DotDict(
            company="Dealer Capital Resources",
            items=[
                DotDict(
                    purchase_receipt="MAT-PRE-2026-00003",
                    expense_account="Custom Expense - DCR",
                )
            ],
        )
        mock_frappe = MagicMock()

        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)

        self.assertEqual(doc["items"][0].expense_account, "Custom Expense - DCR")
        mock_frappe.db.get_value.assert_not_called()

    def test_purchase_order_only_row_is_not_changed(self):
        from dcr.api import accounting

        doc = DotDict(
            company="Dealer Capital Resources",
            items=[
                DotDict(
                    purchase_order="PUR-ORD-2026-00013",
                    expense_account=None,
                )
            ],
        )
        mock_frappe = MagicMock()

        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)

        self.assertIsNone(doc["items"][0].expense_account)
        mock_frappe.db.get_value.assert_not_called()
