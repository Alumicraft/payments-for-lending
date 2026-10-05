"""Payment admission, provider contract, and accounting failure regressions."""
from unittest.mock import MagicMock, patch
import pytest
import requests
from dcr.api.achq_integration import ACHQClient, apply_achq_status_update
from dcr.dcr.doctype.ach_transaction.ach_transaction import ACHTransaction

BILLING = {"Billing_Address1": "123 Test Street", "Billing_City": "Test Town",
    "Billing_State": "CA", "Billing_Zip": "90001", "Billing_Phone": "5550100100",
    "Billing_Email": "synthetic@example.test"}

@pytest.fixture(autouse=True)
def isolate_provider_logging():
    with patch("dcr.api.achq_integration.frappe") as f, patch("dcr.dcr.doctype.ach_settings.ach_settings.loan_is_in_ach_scope", return_value=True), patch("dcr.api.achq_integration.get_customer_billing_details", return_value=BILLING):
        f.throw.side_effect = ValueError
        yield


def transaction(status="Initiated"):
    txn = MagicMock(spec=ACHTransaction)
    for key, value in dict(name="ACH-1", status=status, loan="LOAN-1", customer="DEALER-1", amount=100,
        achq_transaction_id="REF-1", achq_reference_kind="TransAct Reference", bank_account="BANK-1", ach_authorization=None,
        payment_entry=None, loan_repayment=None, payment_due_date="2026-10-06",
        completed_date=None, next_retry_date=None, retry_attempt=0, max_retries=2,
        original_transaction=None, return_code=None, accounting_error=None).items():
        setattr(txn, key, value)
    txn.flags = MagicMock()
    txn._get_payment_account.return_value = ({"custom_authorization_ip": "192.0.2.1"}, "bank_account")
    for method in ("save", "reload", "add_comment", "get", "set"):
        setattr(txn, method, MagicMock())
    for method in ("mark_success", "mark_failed", "cancel_transaction", "should_retry", "create_retry_transaction", "initiate"):
        setattr(txn, method, getattr(ACHTransaction, method).__get__(txn))
    return txn


def client():
    return object.__new__(ACHQClient)


@pytest.mark.parametrize("response", ["", "<html>bad gateway</html>", "[]", "{}", '{"CommandStatus":"Pending"}'])
def test_unrecognized_acknowledgment_is_unknown(response):
    assert client()._parse_response(response)["outcome_unknown"] is True


def test_conflicting_response_is_not_approved():
    assert client()._parse_response('{"CommandStatus":"Declined","ResponseCode":"000"}')["success"] is False


def test_timeout_is_unknown_not_a_refusal():
    with patch("dcr.api.achq_integration.requests.post", side_effect=requests.Timeout), patch.object(ACHQClient, "_get_auth_params", return_value={}):
        assert client()._make_request("ECheck.ProcessPayment", {})["outcome_unknown"]


def test_payment_stores_remote_reference_used_for_void():
    c = client(); c.settings = MagicMock(default_sec_code="CCD")
    c._make_request = MagicMock(return_value={"success": True, "TransAct_ReferenceID": "REF-1", "TransactionID": "INTERNAL-2"})
    result = c.create_payment(100, "TOKEN", "Dealer", "Payment", "ACH-1", billing=BILLING)
    assert result["transaction_id"] == "REF-1"
    c.cancel_payment("REF-1")
    c._make_request.assert_called_with("ECheck.Void", {"Transact_ReferenceID": "REF-1"})


def test_approved_without_reference_requires_reconciliation():
    c = client(); c.settings = MagicMock(default_sec_code="CCD")
    c._make_request = MagicMock(return_value={"success": True})
    assert c.create_payment(100, "TOKEN", "Dealer", "Payment", "ACH-1", billing=BILLING)["outcome_unknown"]


def test_failed_cancellation_keeps_initiated_state():
    txn = transaction()
    with patch("dcr.api.achq_integration.ACHQClient") as provider, patch("dcr.dcr.doctype.ach_transaction.ach_transaction.frappe") as f:
        f.throw.side_effect = ValueError
        provider.return_value.cancel_payment.return_value = {"success": False, "error_message": "Already processing"}
        with pytest.raises(ValueError): txn.cancel_transaction()
    assert txn.status == "Initiated"
    txn.save.assert_not_called()


def test_admission_is_committed_before_provider_call_and_timeout_not_retried():
    txn = transaction("Scheduled")
    txn._get_account_status.return_value = "Active"
    txn._get_token_and_source.return_value = ("TOKEN", "Manual")
    with patch("dcr.api.achq_integration.ACHQClient") as provider, patch("dcr.dcr.doctype.ach_transaction.ach_transaction.frappe") as f:
        def send(**kw):
            assert txn.status == "Outcome Unknown"
            f.db.commit.assert_called_once()
            return {"success": False, "outcome_unknown": True, "error_message": "Timeout"}
        provider.return_value.create_payment.side_effect = send
        assert txn.initiate() is False
    assert txn.status == "Outcome Unknown"
    txn.schedule_retry.assert_not_called()


def test_settlement_failure_does_not_claim_success_or_notify():
    txn = transaction(); txn.create_loan_repayment.return_value = None
    assert txn.mark_success("Settled") is False
    assert txn.status == "Accounting Pending"
    txn.send_notification.assert_not_called()


def test_accounting_recovery_links_submitted_repayment():
    txn = transaction("Accounting Pending")
    txn.create_loan_repayment.return_value = MagicMock(name="ignored")
    txn.create_loan_repayment.return_value.name = "REPAY-1"
    assert txn.mark_success("Settled")
    assert txn.loan_repayment == "REPAY-1"
    assert txn.status == "Success"


def test_duplicate_success_does_not_book_twice():
    txn = transaction("Success"); txn.loan_repayment = "REPAY-1"
    assert txn.mark_success()
    txn.create_loan_repayment.assert_not_called()


def test_late_return_requires_reversal_and_blocks_retry():
    txn = transaction("Success"); txn.loan_repayment = "REPAY-1"
    txn.mark_failed(returned=True, return_code="R01")
    assert txn.status == "Reversal Pending"
    assert txn.next_retry_date is None
    txn.schedule_retry.assert_not_called()
    assert txn.mark_success("Settled") is False


def test_unknown_return_code_is_returned_without_retry():
    txn = transaction()
    txn.mark_failed(returned=True)
    assert txn.status == "Returned"
    txn.schedule_retry.assert_not_called()


@pytest.mark.parametrize("status", ["In-process", "InProcess", "Processing"])
def test_processing_status_spellings_resolve_unknown_submission(status):
    txn = transaction("Outcome Unknown")
    with patch("dcr.api.achq_integration.frappe") as f:
        f.get_doc.return_value = txn
        assert apply_achq_status_update({"Merchant_ReferenceID": "ACH-1", "PaymentStatus": status})
    assert txn.status == "Processing"


def test_poll_does_not_ignore_late_chargeback():
    txn = transaction("Success"); txn.loan_repayment = "REPAY-1"
    with patch("dcr.api.achq_integration.frappe") as f:
        f.get_doc.return_value = txn
        apply_achq_status_update({"Merchant_ReferenceID": "ACH-1", "PaymentStatus": "Charged Back", "ReturnCode": "R10"})
    assert txn.status == "Reversal Pending"


@pytest.mark.parametrize("data", [{"TransAct_ReferenceID": "WRONG"}, {"Amount": "999.00"}])
def test_conflicting_provider_event_is_rejected(data):
    txn = transaction()
    with patch("dcr.api.achq_integration.frappe") as f:
        f.get_doc.return_value = txn
        with pytest.raises(ValueError): apply_achq_status_update(dict(data, Merchant_ReferenceID="ACH-1", PaymentStatus="Settled"))
    txn.create_loan_repayment.assert_not_called()


def test_legacy_payment_entry_blocks_second_gl_receipt():
    txn = transaction(); txn.payment_entry = "PAY-LEGACY"
    with patch("dcr.dcr.doctype.ach_transaction.ach_transaction.frappe") as f:
        assert ACHTransaction.create_loan_repayment(txn) is None
        f.db.rollback.assert_called_once_with(save_point="ach_repayment")
        f.new_doc.assert_not_called()
    assert "Legacy" in txn.accounting_error


def test_reuses_submitted_repayment_without_new_gl():
    txn = transaction(); txn.loan_repayment = "REPAY-1"
    repayment = MagicMock(against_loan="LOAN-1", amount_paid=100, docstatus=1)
    with patch("dcr.dcr.doctype.ach_transaction.ach_transaction.frappe") as f:
        f.db.exists.return_value = None
        f.get_doc.return_value = repayment
        assert ACHTransaction.create_loan_repayment(txn) is repayment
        f.new_doc.assert_not_called()
        repayment.submit.assert_not_called()


def test_submit_error_rolls_back_partial_accounting():
    txn = transaction(); txn.loan_repayment = "REPAY-1"
    repayment = MagicMock(against_loan="LOAN-1", amount_paid=100, docstatus=0)
    repayment.submit.side_effect = ValueError("Missing account")
    with patch("dcr.dcr.doctype.ach_transaction.ach_transaction.frappe") as f:
        f.db.exists.return_value = None; f.get_doc.return_value = repayment
        assert ACHTransaction.create_loan_repayment(txn) is None
        f.db.rollback.assert_called_once_with(save_point="ach_repayment")
    assert txn.accounting_error == "Missing account"
