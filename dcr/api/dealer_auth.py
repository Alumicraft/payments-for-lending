"""Dealer landing route after Frappe's native one-time email-link login."""

import frappe


@frappe.whitelist(allow_guest=True, methods=["GET"])
def login_via_key(key: str):
    # Keep native token validation, consumption, login and rate limiting.
    # Frappe v16's default-app route can otherwise send Website Users to Desk.
    from frappe.www.login import login_via_key as native_login

    result = native_login(key=key)
    response = frappe.local.response
    user = frappe.session.user
    if (
        response.get("type") == "redirect"
        and user != "Guest"
        and frappe.get_cached_value("User", user, "user_type") == "Website User"
    ):
        response["location"] = frappe.utils.get_url("/portal")
    return result
