"""Connecting a bank must not require enabling automatic debits."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dcr.api import achq_integration as api


def test_manual_verification_while_autopay_is_off_only_tokenizes():
    settings = SimpleNamespace(enable_ach_autopay=0, achq_environment="Sandbox",
        achq_merchant_id="synthetic", achq_merchant_gate_id="synthetic",
        get_password=lambda key: "synthetic", default_check_type="Business",
        use_express_verify=True, allow_unknown_accounts=False)
    response = MagicMock(text='{"CommandStatus":"Approved","ACHQToken":"test-token",'
        '"BankName":"Test Bank","ExpressVerify":{"Status":"POS"}}')
    with patch.object(api, "frappe") as f, \
         patch.object(api, "require_staff") as staff, \
         patch.object(api, "_check_rate_limit"), \
         patch.object(api, "_create_bank_account", return_value=SimpleNamespace(name="Test Bank Account", is_default=0)) as create, \
         patch.object(api, "_send_connected_email"), \
         patch.object(api.requests, "post", return_value=response) as post:
        f.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        f.get_single.return_value = settings
        f.db.get_value.return_value = "Synthetic Dealer"
        result = api.setup_bank_account("DEMO", "021000021", "123456789", "Checking", is_default=False)

    assert result["success"] is True
    assert result["is_default"] == 0
    staff.assert_called_once_with("Customer", "DEMO", "write")
    post.assert_called_once()
    payload = post.call_args.kwargs["data"]
    assert payload["Command"] == "ECheck.CreateACHQToken"
    assert payload["TestMode"] == "On"
    assert "Amount" not in payload
    assert create.call_args.kwargs["token"] == "test-token"
    assert create.call_args.kwargs["account_last4"] == "6789"
    assert create.call_args.kwargs["routing_last4"] == "0021"
    assert "account_number" not in create.call_args.kwargs
    assert settings.enable_ach_autopay == 0


def test_payment_client_still_refuses_when_autopay_is_off():
    with patch.object(api, "frappe") as f, patch.object(api.requests, "post") as post:
        f.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        f.get_single.return_value = SimpleNamespace(enable_ach_autopay=0)
        with pytest.raises(ValueError, match="ACH Autopay is not enabled"):
            api.ACHQClient()
        post.assert_not_called()
