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
