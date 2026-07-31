"""Accounting defaults for DCR purchasing flows."""

try:
    import frappe
except ModuleNotFoundError:
    frappe = None


def ensure_purchase_invoice_expense_accounts(doc, method=None):
    """Use the receipt accrual account for invoice rows mapped from receipts.

    ERPNext requires an expense account on every Purchase Invoice Item. Rows
    mapped from a Purchase Receipt should clear the receipt accrual account,
    but a stock item without an Item-level expense default can arrive blank.
    """
    receipt_rows = [
        row
        for row in (doc.get("items") or [])
        if row.get("purchase_receipt") and not row.get("expense_account")
    ]
    if not receipt_rows or not doc.get("company"):
        return

    accrual_account = frappe.db.get_value(
        "Company",
        doc.get("company"),
        "stock_received_but_not_billed",
    )
    if not accrual_account:
        return

    for row in receipt_rows:
        row.expense_account = accrual_account
