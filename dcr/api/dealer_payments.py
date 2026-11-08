"""Read-only Lending records for one dealer-owned loan; no bank/provider calls."""
from collections import defaultdict
from decimal import Decimal

import frappe

CASH_REPAYMENT_TYPES = {"Normal Repayment", "Loan Closure", "Pre Payment", "Advance Payment",
    "Write Off Recovery", "Write Off Settlement", "Charge Payment", "Full Settlement",
    "Partial Settlement", "Principal Adjustment"}


def _amount(value):
    return Decimal(str(value or 0))


def payment_summary(loan, customer_name):
    from dcr.api.dealer_portal import _value, _json_value, _available_fields

    name = _value(loan, "name")
    if not frappe.db.exists("Loan", {"name": name, "applicant": customer_name, "docstatus": 1}):
        # A draft/sanctioned application has no posted payment balance.
        return None
    currency = frappe.db.get_value("Company", _value(loan, "company"), "default_currency")
    today = str(frappe.utils.today())[:10]
    if _value(loan, "disbursed_amount") == 0:
        return {"outstanding_principal": None, "currency": currency, "funded": False,
            "upcoming": [], "history": [], "history_truncated": False, "as_of": today}
    balance = max(0.0, float(pending_principal(name)))
    demands = frappe.get_all("Loan Demand", filters={"loan": name, "docstatus": 1},
        fields=_available_fields("Loan Demand", ["name", "demand_date", "posting_date",
            "demand_subtype", "outstanding_amount", "repayment_schedule_detail", "loan_disbursement"]),
        limit_page_length=0, ignore_permissions=True)
    demanded_rows = set()
    demanded_dates = set()
    due = defaultdict(lambda: {"principal": Decimal(0), "interest": Decimal(0), "charges": Decimal(0), "total": Decimal(0)})
    for row in demands:
        detail = _value(row, "repayment_schedule_detail")
        if detail:
            demanded_rows.add(detail)
            demanded_dates.add((_value(row, "loan_disbursement"),
                str(_json_value(_value(row, "demand_date") or _value(row, "posting_date")))[:10]))
        amount = _amount(_value(row, "outstanding_amount"))
        date = _value(row, "demand_date") or _value(row, "posting_date")
        if not date or amount <= 0:
            continue
        item = due[str(_json_value(date))[:10]]
        subtype = _value(row, "demand_subtype")
        if subtype in ("Principal", "Interest"):
            item[subtype.lower()] += amount
        else:
            item["charges"] += amount
        item["total"] += amount

    schedules = frappe.get_all("Loan Repayment Schedule", filters={"loan": name,
        "docstatus": 1, "status": "Active"}, fields=["name", "loan_disbursement"],
        limit_page_length=0, ignore_permissions=True)
    if schedules:
        funding = {_value(s, "name"): _value(s, "loan_disbursement") for s in schedules}
        rows = frappe.get_all("Repayment Schedule", filters={"parenttype": "Loan Repayment Schedule",
            "parent": ["in", list(funding)]}, fields=["name", "parent", "payment_date", "principal_amount",
            "interest_amount", "total_payment"], order_by="payment_date asc",
            limit_page_length=0, ignore_permissions=True)
        for row in rows:
            date = str(_json_value(_value(row, "payment_date")) or "")[:10]
            # Submitted Loan Demand is authoritative, including zero/paid demands.
            # Older custom Demand Generated flags are not a payment receipt.
            if (not date or date < today or _value(row, "name") in demanded_rows
                    or (funding.get(_value(row, "parent")), date) in demanded_dates):
                continue
            item = due[date]
            item["principal"] += _amount(_value(row, "principal_amount"))
            item["interest"] += _amount(_value(row, "interest_amount"))
            item["total"] += _amount(_value(row, "total_payment"))
    upcoming = [{"date": date, **{field: float(value) for field, value in amounts.items()},
        "outstanding": float(amounts["total"]), "due_status": "Past due" if date < today else "Scheduled"}
        for date, amounts in sorted(due.items())
        if amounts["total"] > 0]
    history = frappe.get_all("Loan Repayment", filters={"against_loan": name, "docstatus": 1},
        fields=_available_fields("Loan Repayment", ["name", "posting_date", "amount_paid", "repayment_type",
            "principal_amount_paid"]),
        order_by="posting_date desc, creation desc", limit_page_length=0, ignore_permissions=True)
    paid = defaultdict(Decimal)
    principal = defaultdict(Decimal)
    for receipt in history:
        day = str(_json_value(_value(receipt, "posting_date")) or "")[:10]
        if day:
            if _value(receipt, "repayment_type") in CASH_REPAYMENT_TYPES:
                paid[day] += _amount(_value(receipt, "amount_paid"))
            principal[day] -= _amount(_value(receipt, "principal_amount_paid"))
    funding = frappe.get_all("Loan Disbursement", filters={"against_loan": name, "docstatus": 1},
        fields=["posting_date", "disbursement_date", "disbursed_amount"],
        limit_page_length=0, ignore_permissions=True)
    for receipt in funding:
        day = str(_json_value(_value(receipt, "posting_date") or _value(receipt, "disbursement_date")))[:10]
        principal[day] += _amount(_value(receipt, "disbursed_amount"))
    return {"outstanding_principal": balance, "currency": currency, "funded": _amount(_value(loan, "disbursed_amount")) > 0,
        "upcoming": upcoming, "history": [{"name": _value(row, "name"),
            "date": _json_value(_value(row, "posting_date")), "amount": _json_value(_value(row, "amount_paid")),
            "type": _value(row, "repayment_type"),
            "is_payment": _value(row, "repayment_type") in CASH_REPAYMENT_TYPES} for row in history],
        "paid_total": float(sum(paid.values(), Decimal(0))),
        "paid_series": _running_series(paid), "principal_series": _running_series(principal),
        "funded_on": min((str(_value(row, "disbursement_date"))[:10] for row in funding), default=None),
        "history_truncated": False, "as_of": frappe.utils.today()}


def _running_series(amounts):
    total = Decimal(0)
    result = []
    for date, amount in sorted(amounts.items()):
        total += amount
        result.append({"date": date, "amount": float(total)})
    return result


def pending_principal(name):
    from lending.loan_management.doctype.loan_repayment.loan_repayment import (
        get_pending_principal_amount,
    )

    return get_pending_principal_amount(frappe.get_doc("Loan", name))
