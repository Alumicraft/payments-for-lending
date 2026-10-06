"""Read-only Lending records for one dealer-owned loan; no bank/provider calls."""
from collections import defaultdict
from decimal import Decimal

import frappe


def _amount(value):
    return Decimal(str(value or 0))


def payment_summary(loan, customer_name):
    from dcr.api.dealer_portal import _value, _json_value, _available_fields

    name = _value(loan, "name")
    if not frappe.db.exists("Loan", {"name": name, "applicant": customer_name, "docstatus": 1}):
        # A draft/sanctioned application has no posted payment balance.
        return None
    required = ("disbursed_amount", "total_principal_paid", "written_off_amount")
    balance = None
    if all(_value(loan, field) is not None for field in required):
        balance = float(max(Decimal(0), _amount(_value(loan, "disbursed_amount"))
                            - _amount(_value(loan, "total_principal_paid"))
                            - _amount(_value(loan, "written_off_amount"))))
    currency = frappe.db.get_value("Company", _value(loan, "company"), "default_currency")
    demands = frappe.get_all("Loan Demand", filters={"loan": name, "docstatus": 1},
        fields=_available_fields("Loan Demand", ["name", "demand_date", "posting_date",
            "demand_subtype", "outstanding_amount", "repayment_schedule_detail"]),
        limit_page_length=0, ignore_permissions=True)
    demanded_rows = set()
    due = defaultdict(lambda: {"principal": Decimal(0), "interest": Decimal(0), "total": Decimal(0)})
    for row in demands:
        detail = _value(row, "repayment_schedule_detail")
        if detail:
            demanded_rows.add(detail)
        amount = _amount(_value(row, "outstanding_amount"))
        date = _value(row, "demand_date") or _value(row, "posting_date")
        if not date or amount <= 0:
            continue
        item = due[str(_json_value(date))[:10]]
        subtype = _value(row, "demand_subtype")
        if subtype in ("Principal", "Interest"):
            item[subtype.lower()] += amount
        item["total"] += amount

    schedules = frappe.get_all("Loan Repayment Schedule", filters={"loan": name,
        "docstatus": 1, "status": "Active"}, pluck="name", limit_page_length=0, ignore_permissions=True)
    if schedules:
        rows = frappe.get_all("Repayment Schedule", filters={"parenttype": "Loan Repayment Schedule",
            "parent": ["in", schedules]}, fields=["name", "payment_date", "principal_amount",
            "interest_amount", "total_payment"], order_by="payment_date asc",
            limit_page_length=0, ignore_permissions=True)
        today = str(frappe.utils.today())[:10]
        for row in rows:
            date = str(_json_value(_value(row, "payment_date")) or "")[:10]
            # Submitted Loan Demand is authoritative, including zero/paid demands.
            # Older custom Demand Generated flags are not a payment receipt.
            if not date or date < today or _value(row, "name") in demanded_rows:
                continue
            item = due[date]
            item["principal"] += _amount(_value(row, "principal_amount"))
            item["interest"] += _amount(_value(row, "interest_amount"))
            item["total"] += _amount(_value(row, "total_payment"))
    upcoming = [{"date": date, **{field: float(value) for field, value in amounts.items()},
        "outstanding": float(amounts["total"])} for date, amounts in sorted(due.items())
        if amounts["total"] > 0]
    history = frappe.get_all("Loan Repayment", filters={"against_loan": name, "docstatus": 1},
        fields=_available_fields("Loan Repayment", ["name", "posting_date", "amount_paid", "repayment_type"]),
        order_by="posting_date desc, creation desc", limit_page_length=101, ignore_permissions=True)
    return {"outstanding_principal": balance, "currency": currency,
        "upcoming": upcoming, "history": [{"name": _value(row, "name"),
            "date": _json_value(_value(row, "posting_date")), "amount": _json_value(_value(row, "amount_paid")),
            "type": _value(row, "repayment_type")} for row in history[:100]],
        "history_truncated": len(history) > 100, "as_of": frappe.utils.today()}
