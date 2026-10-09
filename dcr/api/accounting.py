"""Accounting defaults for DCR purchasing flows."""

try:
    import frappe
except ModuleNotFoundError:
    frappe = None


def ensure_purchase_invoice_expense_accounts(doc, method=None):
    """Fill a blank stock-receipt clearing account only with posted evidence.

    Receipt links alone do not establish an accrual: non-stock items and
    receipts without inventory GL must use their configured expense account.
    Leave those rows to ERPNext's defaults and mandatory-account validation.
    Existing account selections and posted vouchers are never rewritten.
    """
    receipt_rows = [
        row
        for row in (doc.get("items") or [])
        if row.get("purchase_receipt") and not row.get("expense_account")
    ]
    company = doc.get("company")
    if not receipt_rows or not company or doc.get("is_opening") != "No" or doc.get("update_stock"):
        return

    stock_items = set(doc.get_stock_items())
    stock_rows = [
        row for row in receipt_rows
        if row.get("item_code") in stock_items and not row.get("is_fixed_asset")
    ]
    if not stock_rows:
        return

    settings = frappe.db.get_value(
        "Company", company,
        ["enable_perpetual_inventory", "stock_received_but_not_billed"],
        as_dict=True,
    )
    if not settings or not settings.get("enable_perpetual_inventory"):
        return
    accrual_account = settings.get("stock_received_but_not_billed")
    if not accrual_account:
        return

    for row in stock_rows:
        if row.get("po_detail") and frappe.db.get_value(
            "Purchase Order Item", row.get("po_detail"), "delivered_by_supplier"
        ):
            continue
        receipt_credit = frappe.db.get_value(
            "GL Entry",
            {
                "company": company,
                "voucher_type": "Purchase Receipt",
                "voucher_no": row.get("purchase_receipt"),
                "account": accrual_account,
                "is_cancelled": 0,
                "credit": [">", 0],
            },
            "name",
        )
        if receipt_credit:
            row.expense_account = accrual_account
