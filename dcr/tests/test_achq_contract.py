"""Regressions for the token-payment and real CSV reporting contract."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dcr.api.achq_integration import ACHQClient, get_customer_billing_details
from dcr.dcr.doctype.ach_settings.ach_settings import ACHSettings
from dcr.tests.test_ach_settlement import BILLING, transaction


def client(**overrides):
    c = object.__new__(ACHQClient)
    c.settings = SimpleNamespace(default_sec_code="CCD", use_express_verify=False,
        achq_environment="Public Sandbox", ach_scope="Controlled Pilot",
        achq_merchant_id="2001", achq_merchant_gate_id="test", get_password=lambda key: "test")
    for key, value in overrides.items():
        setattr(c.settings, key, value)
    return c


@pytest.fixture(autouse=True)
def isolate_frappe():
    with patch("dcr.api.achq_integration.frappe") as f:
        f.throw.side_effect = ValueError
        yield


@pytest.mark.parametrize("source,expected", [("Manual", "ACHQ"), ("ACHQ", "ACHQ"), (None, "ACHQ"), ("Plaid", "Plaid")])
def test_required_token_payload_and_internal_reference(source, expected):
    params = client().payment_parameters(1, "TOKEN", "Synthetic Dealer", "Test", "ACH-1",
        token_source=source, billing=BILLING)
    assert params["TokenSource"] == expected
    assert params["Merchant_ReferenceID"] == params["Provider_TransactionID"] == "ACH-1"
    assert params["SendEmailToCustomer"] == "No"
    assert params["Run_ExpressVerify"] == "No"
    assert all(params[key] == value for key, value in BILLING.items())


@pytest.mark.parametrize("missing", list(BILLING))
def test_missing_billing_blocks_before_network(missing):
    c = client(); c._make_request = MagicMock()
    billing = dict(BILLING); billing.pop(missing)
    with pytest.raises(ValueError):
        c.create_payment(1, "TOKEN", "Synthetic Dealer", "Test", "ACH-1", billing=billing)
    c._make_request.assert_not_called()


def test_web_requires_captured_authorization_ip():
    c = client(default_sec_code="WEB")
    with pytest.raises(ValueError):
        c.payment_parameters(1, "TOKEN", "Dealer", "Test", "ACH-1", billing=BILLING)
    assert c.payment_parameters(1, "TOKEN", "Dealer", "Test", "ACH-1",
        billing=BILLING, customer_ip="192.0.2.1")["Customer_IPAddress"] == "192.0.2.1"


def test_unknown_token_source_is_refused():
    with pytest.raises(ValueError):
        client().payment_parameters(1, "TOKEN", "Dealer", "Test", "ACH-1", billing=BILLING, token_source="Unknown")


def test_profile_error_does_not_admit_uncertain_debit():
    txn = transaction("Scheduled")
    txn._get_account_status.return_value = "Active"
    txn._get_token_and_source.return_value = ("TOKEN", "Manual")
    with patch("dcr.api.achq_integration.ACHQClient") as provider, \
         patch("dcr.api.achq_integration.get_customer_billing_details", return_value={}), \
         patch("dcr.dcr.doctype.ach_settings.ach_settings.loan_is_in_ach_scope", return_value=True), \
         patch("dcr.dcr.doctype.ach_transaction.ach_transaction.frappe") as f:
        provider.return_value.payment_parameters.side_effect = ValueError("Missing billing")
        with pytest.raises(ValueError):
            txn.initiate()
        f.db.commit.assert_not_called()
        provider.return_value.create_payment.assert_not_called()
    assert txn.status == "Scheduled"
    txn.save.assert_not_called()


def test_billing_uses_primary_address_and_contact_without_fabrication():
    with patch("dcr.api.lending._get_customer_address_details", return_value={"address_line_1": "Test", "city": "Town"}), \
         patch("dcr.api.lending._get_customer_contact_details", return_value={"email": "synthetic@example.test"}):
        billing = get_customer_billing_details("DEALER-1")
    assert billing["Billing_Address1"] == "Test"
    assert billing["Billing_Email"] == "synthetic@example.test"
    assert billing["Billing_Zip"] is None
    assert billing["Billing_Phone"] is None


def test_direct_merchant_csv_preserves_reference_status_and_quoted_explanation():
    report = '36177960,ACH-1,Returned,10/05/2026 13:17:50,Returned,R01,"NSF, insufficient funds",,,\r\n'
    result = client()._parse_status_response(report)
    assert result["success"]
    assert result["transactions"] == [{"TransAct_ReferenceID": "36177960", "Merchant_ReferenceID": "ACH-1",
        "Event": "Returned", "EventDate": "10/05/2026 13:17:50", "PaymentStatus": "Returned",
        "ReturnCode": "R01", "ReturnDescription": "NSF, insufficient funds"}]


def test_platform_csv_filters_other_merchants():
    result = client()._parse_status_response(
        "36177960,ACH-1,2001,Created,10/05/2026 13:17:50,Scheduled,,,,,\n"
        "123,OTHER,999,Created,10/05/2026 13:17:50,Scheduled,,,,,\n")
    assert result["success"]
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["Merchant_ReferenceID"] == "ACH-1"
    assert result["transactions"][0]["PaymentStatus"] == "Scheduled"


def test_missing_remote_reference_is_reported_and_does_not_hide_valid_events():
    with patch("dcr.api.achq_integration.frappe") as f:
        result = client()._parse_status_response(
            ",UNKNOWN,Created,10/05/2026 13:17:50,Scheduled,,,,,\n"
            "36177960,ACH-1,Created,10/05/2026 13:17:50,Scheduled,,,,,\n")
        f.logger.return_value.warning.assert_called_once()
    assert result["success"]
    assert result["unidentifiable_rows"] == 1
    assert len(result["transactions"]) == 1


@pytest.mark.parametrize("body", ["", "<html>unavailable</html>", "123,bad,row", '"unterminated',
    "123,ACH-1,Created,10/05/2026 13:17:50,,,,,,"])
def test_malformed_report_is_explicit_failure(body):
    result = client()._parse_status_response(body)
    assert not result["success"]
    assert result.get("error_message")


def test_json_provider_refusal_is_preserved():
    result = client()._parse_status_response('{"CommandStatus":"Declined","ResponseCode":"103","Description":"Refused"}')
    assert result["success"] is False
    assert result["error_code"] == "103"


def test_status_query_routes_real_http_csv_to_report_parser():
    response = MagicMock(text="36177960,ACH-1,Created,10/05/2026 13:17:50,Scheduled,,,,,\n")
    with patch("dcr.api.achq_integration.requests.post", return_value=response) as post:
        result = client().get_status_by_date(date(2026, 10, 5))
    assert result["success"]
    assert result["transactions"][0]["TransAct_ReferenceID"] == "36177960"
    assert post.call_args.kwargs["data"]["TrackingDate"] == "10052026"


def test_public_sandbox_omits_testmode_but_development_retains_it():
    assert "TestMode" not in client()._get_auth_params()
    assert client(achq_environment="Sandbox")._get_auth_params()["TestMode"] == "On"


@pytest.mark.parametrize("changes", [{"achq_merchant_id": "LIVE"}, {"achq_merchant_gate_id": "LIVE"}, {"get_password": lambda key: "LIVE"}])
def test_public_sandbox_cannot_send_live_credentials(changes):
    with pytest.raises(ValueError):
        client(**changes)._get_auth_params()


def test_public_sandbox_cannot_expand_payment_scope():
    with pytest.raises(ValueError):
        client(ach_scope="All Eligible Loans").payment_parameters(1, "TOKEN", "Dealer", "Test", "ACH-1", billing=BILLING)


def test_settings_refuse_invalid_public_sandbox_credentials_even_while_disabled():
    settings = MagicMock(enable_ach_autopay=False, achq_environment="Public Sandbox",
        achq_merchant_id="LIVE", achq_merchant_gate_id="test", ach_scope="Controlled Pilot")
    settings.get_password.return_value = "test"
    with patch("dcr.dcr.doctype.ach_settings.ach_settings.frappe") as f:
        f.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            ACHSettings.validate(settings)
