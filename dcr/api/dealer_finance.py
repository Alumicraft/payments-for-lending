"""Financial readback after the portal has resolved the signed-in dealer."""
from collections import defaultdict
from decimal import Decimal

import frappe

from dcr.api.dealer_payments import CASH_REPAYMENT_TYPES, _amount, _running_series, pending_principal


def credit_usage(customer_name):
    """Use the same reserved-credit calculation as staff application approval."""
    result = frappe.db.sql("""
        SELECT COALESCE(SUM(loan_amount - COALESCE(total_principal_paid, 0)), 0) AS total
        FROM `tabLoan`
        WHERE applicant = %s AND applicant_type = 'Customer'
        AND status IN ('Disbursed', 'Partially Disbursed', 'Active')
        """, (customer_name,), as_dict=True)
    return result[0].total if result else 0


def financial_summary(customer_name, balances=None):
    loans = frappe.get_all("Loan", filters={"applicant": customer_name,
        "applicant_type": "Customer", "docstatus": 1},
        fields=["name", "status", "disbursed_amount"], limit_page_length=0, ignore_permissions=True)
    names = [row.name for row in loans if _amount(row.disbursed_amount) > 0]
    balances = balances or {}
    outstanding = sum((max(Decimal(0), _amount(balances[name] if balances.get(name) is not None
        else pending_principal(name))) for name in names), Decimal(0))
    mifa = frappe.db.get_value("MIFA", {"customer": customer_name, "docstatus": 1},
        ["name", "credit_limit"], as_dict=True, order_by="mifa_date desc, creation desc")
    limit = _amount(mifa.credit_limit) if mifa and mifa.credit_limit not in (None, "") else None
    used = _amount(credit_usage(customer_name))
    principal, paid = defaultdict(Decimal), defaultdict(Decimal)
    if names:
        for row in frappe.get_all("Loan Disbursement", filters={"against_loan": ["in", names], "docstatus": 1},
                fields=["posting_date", "disbursement_date", "disbursed_amount"],
                limit_page_length=0, ignore_permissions=True):
            day = row.posting_date or row.disbursement_date
            if day:
                principal[str(day)[:10]] += _amount(row.disbursed_amount)
        for row in frappe.get_all("Loan Repayment", filters={"against_loan": ["in", names], "docstatus": 1},
                fields=["posting_date", "principal_amount_paid", "amount_paid", "repayment_type"],
                limit_page_length=0, ignore_permissions=True):
            if not row.posting_date:
                continue
            day = str(row.posting_date)[:10]
            principal[day] -= _amount(row.principal_amount_paid)
            if row.repayment_type in CASH_REPAYMENT_TYPES:
                paid[day] += _amount(row.amount_paid)
    return {"available": True, "outstanding": float(outstanding),
        "credit_limit": float(limit) if limit is not None else None,
        "credit_used": float(used),
        "available_credit": float(limit - used) if limit is not None else None,
        "funded_loans": len(names), "principal_series": _running_series(principal),
        "paid_series": _running_series(paid), "paid_total": float(sum(paid.values(), Decimal(0)))}
