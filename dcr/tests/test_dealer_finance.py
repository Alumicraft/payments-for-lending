"""Account totals include all owned submitted records, including long histories."""
from types import SimpleNamespace as Row
from unittest.mock import patch

from dcr.api import dealer_finance as finance


@patch.object(finance, "pending_principal", side_effect=[1000, 0])
@patch.object(finance, "frappe")
def test_owned_balances_and_full_receipt_history(frappe, pending):
    frappe.db.get_value.return_value = Row(name="MIFA-A", credit_limit=5000)
    records = {
        "Loan": [Row(name="A", status="Disbursed", disbursed_amount=1102),
                 Row(name="B", status="Closed", disbursed_amount=100)],
        "Loan Disbursement": [Row(posting_date="2026-01-01", disbursement_date="2026-01-01", disbursed_amount=1202)],
        "Loan Repayment": [Row(posting_date="2026-01-02", amount_paid=1, principal_amount_paid=1, repayment_type="Normal Repayment") for _ in range(102)]
            + [Row(posting_date="2026-01-03", amount_paid=100, principal_amount_paid=100, repayment_type="Pre Payment"),
               Row(posting_date="2026-01-03", amount_paid=50, principal_amount_paid=0, repayment_type="Interest Waiver")],
    }
    frappe.get_all.side_effect = lambda doctype, **kwargs: records[doctype]
    result = finance.financial_summary("DEALER-A")
    assert result["outstanding"] == 1000
    assert result["available_credit"] == 4000
    assert result["paid_total"] == 202
    assert result["paid_series"] == [{"date": "2026-01-02", "amount": 102}, {"date": "2026-01-03", "amount": 202}]
    assert result["principal_series"][-1] == {"date": "2026-01-03", "amount": 1000}
    assert result["funded_loans"] == 2
    for call in frappe.get_all.call_args_list:
        assert call.kwargs["limit_page_length"] == 0
        filters = call.kwargs["filters"]
        assert filters["docstatus"] == 1
        if call.args[0] == "Loan":
            assert filters["applicant"] == "DEALER-A"
        else:
            assert filters["against_loan"] == ["in", ["A", "B"]]
    assert not hasattr(finance.financial_summary, "is_whitelisted")


@patch.object(finance, "frappe")
def test_missing_credit_limit_is_unavailable_instead_of_zero(frappe):
    frappe.get_all.return_value = []
    frappe.db.get_value.return_value = None
    result = finance.financial_summary("DEALER-A")
    assert result["credit_limit"] is None
    assert result["available_credit"] is None
    assert result["outstanding"] == result["paid_total"] == 0
    assert result["principal_series"] == []
