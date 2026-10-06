"""Dealer payment readback: ownership and posted demand reconciliation."""
from unittest.mock import patch

from dcr.api import dealer_payments as payments
from dcr.api import dealer_portal as portal


@patch.object(payments, "frappe")
def test_unowned_or_unsubmitted_loan_never_reads_payment_records(frappe):
    frappe.db.exists.return_value = False
    assert payments.payment_summary({"name": "OTHER-LOAN"}, "DEALER-A") is None
    frappe.get_all.assert_not_called()
    frappe.db.exists.assert_called_once_with("Loan", {
        "name": "OTHER-LOAN", "applicant": "DEALER-A", "docstatus": 1})


@patch.object(portal, "_available_fields", side_effect=lambda doctype, fields: fields)
@patch.object(payments, "frappe")
def test_paid_demands_override_old_unchecked_flags_and_remaining_amount_is_not_full_emi(frappe, fields):
    frappe.db.exists.return_value = True
    frappe.db.get_value.return_value = "USD"
    frappe.utils.today.return_value = "2026-10-06"
    data = {
        "Loan Demand": [
            {"repayment_schedule_detail": "PAID", "demand_date": "2026-10-31", "outstanding_amount": 0},
            {"repayment_schedule_detail": "PARTIAL", "demand_date": "2026-09-30", "outstanding_amount": 700, "demand_subtype": "Interest"},
        ],
        "Loan Repayment Schedule": ["RS-A"],
        "Repayment Schedule": [
            {"name": "PAID", "payment_date": "2026-10-31", "total_payment": 2200, "demand_generated": 0},
            {"name": "PARTIAL", "payment_date": "2026-09-30", "total_payment": 2200, "demand_generated": 0},
            {"name": "FUTURE", "payment_date": "2026-11-30", "total_payment": 2200, "interest_amount": 2200},
        ],
        "Loan Repayment": [{"name": "PAY-A", "posting_date": "2026-10-01", "amount_paid": 1500, "repayment_type": "Normal Repayment"}],
    }
    frappe.get_all.side_effect = lambda doctype, **kwargs: data[doctype]
    result = payments.payment_summary({"name": "LOAN-A", "company": "DCR", "disbursed_amount": 220000,
        "total_principal_paid": 5000, "written_off_amount": 1000}, "DEALER-A")
    assert result["outstanding_principal"] == 214000
    assert result["upcoming"] == [
        {"date": "2026-09-30", "principal": 0.0, "interest": 700.0, "charges": 0.0, "total": 700.0, "outstanding": 700.0, "due_status": "Past due"},
        {"date": "2026-11-30", "principal": 0.0, "interest": 2200.0, "charges": 0.0, "total": 2200.0, "outstanding": 2200.0, "due_status": "Scheduled"}]
    assert result["history"][0]["amount"] == 1500
    assert result["currency"] == "USD"
    calls = {call.args[0]: call.kwargs for call in frappe.get_all.call_args_list}
    assert calls["Loan Demand"]["filters"] == {"loan": "LOAN-A", "docstatus": 1}
    assert calls["Loan Repayment"]["filters"] == {"against_loan": "LOAN-A", "docstatus": 1}
    assert calls["Repayment Schedule"]["filters"]["parent"] == ["in", ["RS-A"]]


@patch.object(payments, "frappe")
def test_approved_unfunded_loan_has_no_posted_balance_or_payment_schedule(frappe):
    frappe.db.exists.return_value = True
    result = payments.payment_summary({"name": "LOAN-A", "disbursed_amount": 0,
        "total_principal_paid": 0, "written_off_amount": 0}, "DEALER-A")
    assert result["funded"] is False
    assert result["outstanding_principal"] is None
    assert result["upcoming"] == []
    frappe.get_all.assert_not_called()


@patch.object(portal, "_available_fields", side_effect=lambda doctype, fields: fields)
@patch.object(payments, "frappe")
def test_charge_demands_are_included_in_displayed_breakdown(frappe, fields):
    frappe.db.exists.return_value = True
    frappe.utils.today.return_value = "2026-10-06"
    frappe.get_all.side_effect = lambda doctype, **kwargs: [{"demand_date": "2026-10-01",
        "outstanding_amount": 75, "demand_subtype": "Penalty"}] if doctype == "Loan Demand" else []
    result = payments.payment_summary({"name": "LOAN-A", "disbursed_amount": 1000,
        "total_principal_paid": 0, "written_off_amount": 0}, "DEALER-A")
    row = result["upcoming"][0]
    assert row["principal"] + row["interest"] + row["charges"] == row["total"] == 75
    assert row["due_status"] == "Past due"


@patch.object(portal, "_latest_related", side_effect=[None, {"name": "LOAN-A", "loan_amount": 1000}])
@patch.object(payments, "payment_summary", side_effect=ValueError("one schedule query failed"))
@patch.object(portal, "frappe")
def test_unavailable_payments_do_not_hide_owned_request_or_invent_zero(frappe, readback, related):
    result = portal._loan_summary("HBR-A", "DEALER-A")
    assert result["name"] == "LOAN-A"
    assert result["principal"] == 1000
    assert result["payments_summary"] is None
    assert result["payments_unavailable"] is True
    frappe.log_error.assert_called_once()


@patch.object(portal, "frappe")
def test_save_only_review_remains_editable_but_acceptance_and_cancellation_lock(frappe):
    frappe.throw.side_effect = ValueError
    import pytest
    for state in ("Draft", "Submitted for Review", "Changes Requested"):
        portal._require_editable_hbr({"docstatus": 0, "custom_portal_status": state})
    for docstatus, state in ((1, "Accepted"), (2, "Draft"), (0, "Accepted")):
        with pytest.raises(ValueError):
            portal._require_editable_hbr({"docstatus": docstatus, "custom_portal_status": state})
    assert portal._portal_status({"docstatus": 2, "custom_portal_status": "Accepted"}) == "Cancelled"


@patch.object(portal, "_hbr_document_items", return_value=[])
@patch.object(portal, "_has_field", return_value=True)
@patch.object(portal, "_loan_summary", return_value={"status": "Not Started"})
def test_legacy_review_states_share_display_but_preserve_identity_and_edit_data(summary, *mocks):
    for state in ("Draft", "Submitted for Review", "Changes Requested"):
        result = portal._serialize_hbr({"name": "HBR-A", "docstatus": 0,
            "custom_portal_status": state, "quote_no": "QUOTE-A"}, {"name": "DEALER-A"})
        assert result["name"] == "HBR-A"
        assert result["portal_status"] == "In review"
        assert result["editable"]["quote_no"] == "QUOTE-A"
    summary.assert_called_with("HBR-A", "DEALER-A")


@patch.object(portal, "_latest_related", return_value={"name": "LOAN-A", "status": "Disbursed"})
@patch.object(portal, "_get_owned_hbr", return_value={"name": "HBR-A"})
@patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
@patch.object(portal, "frappe")
def test_payoff_request_is_owned_durable_and_deduplicated_without_sending(frappe, identity, owned, related):
    frappe.utils.today.return_value = "2026-10-06"
    frappe.db.exists.return_value = False
    result = portal.request_payoff_letter("HBR-A")
    assert result["recorded"] is True
    related.assert_called_once_with("Loan", {"home_build_request": "HBR-A", "applicant": "DEALER-A", "docstatus": 1}, ["name", "status"])
    notice = frappe.get_doc.call_args.args[0]
    assert notice["status"] == "Recorded"
    assert notice["customer"] == "DEALER-A"
    assert notice["audience"] == "Staff"
    frappe.sendmail.assert_not_called()
    frappe.get_print.assert_not_called()
    frappe.get_doc.reset_mock()
    frappe.db.exists.return_value = True
    assert portal.request_payoff_letter("HBR-A")["already_recorded"] is True
    frappe.get_doc.assert_not_called()


@patch.object(portal, "_get_owned_hbr", side_effect=ValueError)
@patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
@patch.object(portal, "_latest_related")
def test_other_dealer_payoff_request_cannot_reach_loan_or_email(related, identity, owned):
    import pytest
    with pytest.raises(ValueError):
        portal.request_payoff_letter("OTHER-HBR")
    related.assert_not_called()
