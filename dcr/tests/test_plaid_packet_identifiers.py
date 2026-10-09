"""Only the selected account's masked identifiers may reach the packet."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest


@pytest.mark.parametrize("selected_routing", ["021000021", None, "123", "not-routing", "０２１００００２１", "other-account-only"])
def test_plaid_connection_retains_selected_routing_mask_without_raw_numbers(selected_routing):
    from dcr.api import achq_integration as api

    fake = MagicMock()
    def reject(message):
        raise ValueError(message)
    fake.throw.side_effect = reject
    fake.get_single.return_value = SimpleNamespace(
        has_plaid_credentials=lambda: True, plaid_client_id="test-client",
        get_password=lambda _: "test-secret", get_plaid_base_url=lambda: "https://sandbox.plaid.com")
    auth_payload = {
        "accounts": [{"account_id": "selected", "name": "Sandbox Checking", "subtype": "checking", "mask": "6789"}],
        "numbers": {"ach": [
            {"account_id": "other", "routing": "011401533", "account": "99999999"},
            {"account_id": "selected", "routing": selected_routing, "account": "123456789"}]},
        "item": {}}
    if selected_routing == "other-account-only":
        auth_payload["numbers"]["ach"] = auth_payload["numbers"]["ach"][:1]

    def response(url, **kwargs):
        payload = auth_payload if url.endswith(("/auth/get", "/accounts/get")) else (
            {"access_token": "test-access"} if url.endswith("/item/public_token/exchange") else
            {"processor_token": "test-processor"})
        result = MagicMock()
        result.json.return_value = payload
        return result

    with patch.object(api, "frappe", fake), patch.object(api, "require_staff"), \
            patch.object(api, "_check_rate_limit"), patch.object(api.requests, "post", side_effect=response) as post, \
            patch.object(api, "_create_bank_account", return_value=SimpleNamespace(name="TEST BANK", is_default=1)) as create, \
            patch.object(api, "_send_connected_email"):
        if selected_routing != "021000021":
            with pytest.raises(ValueError, match="selected account"):
                api.process_plaid_callback("test-public", "selected", "DEMO DEALER")
            create.assert_not_called()
            fake.db.commit.assert_not_called()
            assert not any(call.args[0].endswith("/processor/token/create") for call in post.call_args_list)
            return
        result = api.process_plaid_callback("test-public", "selected", "DEMO DEALER")

    assert create.call_args.kwargs["routing_last4"] == "0021"
    assert create.call_args.kwargs["account_last4"] == "6789"
    assert any(call.args[0].endswith("/auth/get") for call in post.call_args_list)
    auth_call = next(call for call in post.call_args_list if call.args[0].endswith("/auth/get"))
    assert auth_call.kwargs["json"]["options"] == {"account_ids": ["selected"]}
    assert "021000021" not in repr(create.call_args)
    assert "123456789" not in repr(create.call_args)
    assert result["success"] is True
