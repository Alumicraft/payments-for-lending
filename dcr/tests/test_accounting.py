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
            is_opening="No",
            items=[
                DotDict(
                    item_code="Stock Home",
                    purchase_receipt="MAT-PRE-2026-00003",
                    expense_account=None,
                )
            ],
        )
        doc.get_stock_items = lambda: ["Stock Home"]
        mock_frappe = MagicMock()
        mock_frappe.db.get_value.side_effect = [DotDict(
            enable_perpetual_inventory=1,
            stock_received_but_not_billed="Stock Received But Not Billed - DCR",
        ), "TEST-RECEIPT-CREDIT"]

        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)

        self.assertEqual(
            doc["items"][0].expense_account,
            "Stock Received But Not Billed - DCR",
        )
        self.assertEqual(mock_frappe.db.get_value.call_count, 2)
        gl_filter = mock_frappe.db.get_value.call_args.args[1]
        self.assertEqual(gl_filter["voucher_type"], "Purchase Receipt")
        self.assertEqual(gl_filter["voucher_no"], "MAT-PRE-2026-00003")
        self.assertEqual(gl_filter["company"], "Dealer Capital Resources")
        self.assertEqual(gl_filter["account"], "Stock Received But Not Billed - DCR")
        self.assertEqual(gl_filter["is_cancelled"], 0)
        self.assertEqual(gl_filter["credit"], [">", 0])

    def test_non_stock_receipt_does_not_inherit_stock_clearing(self):
        from dcr.api import accounting

        doc = DotDict(company="DCR", is_opening="No", items=[
            DotDict(item_code="Non-stock Home", purchase_receipt="TEST-PR", expense_account=None)
        ])
        doc.get_stock_items = lambda: []
        mock_frappe = MagicMock()
        mock_frappe.db.get_value.side_effect = lambda doctype, name, fields, **kwargs: (
            "Stock Clearing - DCR" if isinstance(fields, str) else DotDict(
                enable_perpetual_inventory=1, stock_received_but_not_billed="Stock Clearing - DCR"
            )
        )
        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)
        self.assertIsNone(doc["items"][0].expense_account,
                          "A non-stock receipt must not manufacture a stock-clearing debit")

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

    def test_stock_receipt_without_posted_credit_stays_unconfigured(self):
        from dcr.api import accounting
        row = DotDict(item_code="Stock Home", purchase_receipt="TEST-PR", expense_account=None)
        doc = DotDict(company="DCR", is_opening="No", items=[row])
        doc.get_stock_items = lambda: ["Stock Home"]
        mock_frappe = MagicMock()
        mock_frappe.db.get_value.side_effect = [DotDict(
            enable_perpetual_inventory=1, stock_received_but_not_billed="Stock Clearing - DCR"
        ), None]
        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)
        self.assertIsNone(row.expense_account)

    def test_native_inventory_exceptions_do_not_get_stock_clearing(self):
        from dcr.api import accounting
        for exception in ["perpetual_off", "opening", "update_stock", "fixed_asset", "drop_ship",
                          "missing_company_account", "missing_company"]:
            with self.subTest(exception=exception):
                row = DotDict(item_code="Stock Home", purchase_receipt="TEST-PR", expense_account=None)
                doc = DotDict(company="DCR", is_opening="No", items=[row])
                doc.get_stock_items = lambda: ["Stock Home"]
                settings = DotDict(enable_perpetual_inventory=1,
                                   stock_received_but_not_billed="Stock Clearing - DCR")
                if exception == "perpetual_off": settings.enable_perpetual_inventory = 0
                if exception == "opening": doc.is_opening = "Yes"
                if exception == "update_stock": doc.update_stock = 1
                if exception == "fixed_asset": row.is_fixed_asset = 1
                if exception == "drop_ship": row.po_detail = "TEST-PO-ROW"
                if exception == "missing_company_account": settings.stock_received_but_not_billed = None
                if exception == "missing_company": doc.company = None
                mock_frappe = MagicMock()
                mock_frappe.db.get_value.side_effect = [settings, 1]
                with patch.object(accounting, "frappe", mock_frappe):
                    accounting.ensure_purchase_invoice_expense_accounts(doc)
                self.assertIsNone(row.expense_account)
                self.assertFalse(any(call.args[0] == "GL Entry"
                                     for call in mock_frappe.db.get_value.call_args_list))

    def test_mixed_invoice_preserves_non_stock_and_existing_accounts(self):
        from dcr.api import accounting
        rows = [
            DotDict(item_code="Stock Home", purchase_receipt="TEST-PR", expense_account=None),
            DotDict(item_code="Service", purchase_receipt="TEST-PR", expense_account=None),
            DotDict(item_code="Stock Home", purchase_receipt="TEST-PR", expense_account="Chosen Account"),
        ]
        doc = DotDict(company="DCR", is_opening="No", items=rows)
        doc.get_stock_items = lambda: ["Stock Home"]
        mock_frappe = MagicMock()
        mock_frappe.db.get_value.side_effect = [DotDict(
            enable_perpetual_inventory=1, stock_received_but_not_billed="Stock Clearing - DCR"
        ), "TEST-GL"]
        with patch.object(accounting, "frappe", mock_frappe):
            accounting.ensure_purchase_invoice_expense_accounts(doc)
        self.assertEqual(rows[0].expense_account, "Stock Clearing - DCR")
        self.assertIsNone(rows[1].expense_account)
        self.assertEqual(rows[2].expense_account, "Chosen Account")
