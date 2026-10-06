"""Bank linking must not require switching on automatic ACH debits."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize("autopay", [False, True])
@pytest.mark.parametrize("credentials", [False, True])
def test_plaid_availability_uses_credentials_without_changing_autopay(autopay, credentials):
    from dcr.dcr.doctype.ach_settings.ach_settings import is_ach_enabled, is_plaid_enabled

    settings = SimpleNamespace(enable_ach_autopay=autopay, has_plaid_credentials=lambda: credentials)
    with patch("dcr.dcr.doctype.ach_settings.ach_settings.get_ach_settings", return_value=settings):
        assert is_plaid_enabled() is credentials
        assert is_ach_enabled() is autopay
    assert settings.enable_ach_autopay is autopay


def test_achq_execution_stays_blocked_when_plaid_is_configured_but_autopay_off():
    from dcr.api.achq_integration import ACHQClient

    fake = MagicMock()
    fake.get_single.return_value = SimpleNamespace(enable_ach_autopay=False)
    fake.throw.side_effect = ValueError("ACH Autopay is not enabled")
    with patch("dcr.api.achq_integration.frappe", fake), patch("dcr.api.achq_integration.requests.post") as post:
        with pytest.raises(ValueError, match="ACH Autopay is not enabled"):
            ACHQClient()
    post.assert_not_called()


def test_bank_only_connection_does_not_send_the_automatic_debit_confirmation():
    from dcr.api.achq_integration import _send_connected_email

    with patch("dcr.dcr.doctype.ach_settings.ach_settings.is_ach_enabled", return_value=False), \
            patch("dcr.api.dcr_email.send_autopay_connected") as send:
        _send_connected_email("DEMO DEALER", "Sandbox Bank", "1234")
    send.assert_not_called()


@pytest.mark.parametrize("already_connected", [False, True])
def test_sandbox_page_context_keeps_environment_and_disabled_autopay(already_connected):
    from dcr.www.plaid_setup import get_context

    fake = MagicMock()
    fake.form_dict = {"customer": "DEMO DEALER", "token": "test-token"}
    fake.db.exists.side_effect = lambda dt, *args: True if dt == "Customer" else already_connected
    fake.db.get_value.return_value = "Demo Dealer"
    fake.get_single.return_value = SimpleNamespace(enable_ach_autopay=0, plaid_environment="Sandbox")
    context = SimpleNamespace()
    with patch("dcr.www.plaid_setup.frappe", fake), \
            patch("dcr.www.plaid_setup.verify_plaid_token", return_value=True), \
            patch("dcr.api.achq_integration.is_plaid_available", return_value={"available": True}):
        get_context(context)
    assert context.plaid_environment == "Sandbox"
    assert context.autopay_enabled is False
    assert getattr(context, "already_connected", False) is already_connected
    assert getattr(context, "show_plaid", False) is not already_connected
