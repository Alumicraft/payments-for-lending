"""Native authentication must succeed before dealer landing routes apply."""

import types
from unittest.mock import MagicMock, patch

import pytest

from dcr.api import dealer_auth


def run_native_login(response, user="dealer@example.test", user_type="Website User", error=None):
    native = MagicMock(side_effect=error)
    module = types.ModuleType("frappe.www.login")
    module.login_via_key = native
    with patch.dict("sys.modules", {"frappe.www.login": module}), patch.object(dealer_auth, "frappe") as frappe:
        frappe.local.response = response
        frappe.session.user = user
        frappe.get_cached_value.return_value = user_type
        frappe.utils.get_url.side_effect = lambda path: "https://dealer.example.test" + path
        if error:
            with pytest.raises(type(error), match="native refusal"):
                dealer_auth.login_via_key("ONE-TIME-KEY")
        else:
            dealer_auth.login_via_key("ONE-TIME-KEY")
        native.assert_called_once_with(key="ONE-TIME-KEY")
        return frappe


def test_valid_website_login_returns_to_portal():
    response = {"type": "redirect", "location": "https://dealer.example.test/desk"}
    run_native_login(response)
    assert response["location"] == "https://dealer.example.test/portal"


def test_system_user_keeps_native_destination():
    response = {"type": "redirect", "location": "/desk"}
    run_native_login(response, user_type="System User")
    assert response["location"] == "/desk"


def test_expired_key_does_not_redirect_existing_authenticated_user():
    response = {"type": "page", "http_status_code": 403}
    frappe = run_native_login(response)
    assert "location" not in response
    frappe.get_cached_value.assert_not_called()


def test_guest_cannot_get_portal_redirect():
    response = {"type": "redirect", "location": "/login"}
    frappe = run_native_login(response, user="Guest")
    assert response["location"] == "/login"
    frappe.get_cached_value.assert_not_called()


def test_native_rate_limit_or_auth_refusal_propagates():
    response = {}
    frappe = run_native_login(response, error=ValueError("native refusal"))
    assert response == {}
    frappe.get_cached_value.assert_not_called()
