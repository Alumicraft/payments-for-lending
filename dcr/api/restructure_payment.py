"""Keep DCR's saved restructure quote consistent with its dated schedule."""

try:
    import frappe
except ModuleNotFoundError:
    frappe = None


def sync_schedule_payment(doc, method=None):
    saving = doc.get("docstatus") == 0 or (doc.get("docstatus") == 1 and method == "before_submit")
    if not saving or doc.get("restructure_type") != "Normal Restructure":
        return
    product = frappe.db.get_value("Loan", doc.loan, "loan_product")
    if frappe.db.get_value("Loan Product", product, "custom_schedule_type") != "Interest Only Then Percent Principal":
        return
    amount = frappe.db.get_value(
        "Loan Repayment Schedule",
        {"loan_restructure": doc.name, "loan": doc.loan, "docstatus": 0},
        "monthly_repayment_amount",
    )
    if amount is None:
        frappe.throw("The generated floorplan schedule is required before saving the restructure payment.")
    if doc.get("new_monthly_repayment_amount") != amount:
        if method == "before_submit":
            doc.set("new_monthly_repayment_amount", amount)
        else:
            doc.db_set("new_monthly_repayment_amount", amount, update_modified=False)
