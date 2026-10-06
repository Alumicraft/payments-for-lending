"""Dealer portal website page."""

import frappe


no_cache = 1


def get_context(context):
    if frappe.session.user in (None, "Guest", "guest"):
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    context.title = "Dealer Portal"
    context.portal_user = frappe.session.user
    # Use the native login page's resolver, including its configured fallbacks.
    context.dealer_logo = frappe.get_attr("frappe.core.doctype.navbar_settings.navbar_settings.get_app_logo")()
    from dcr.api.dealer_portal import _support_url
    context.support_url = _support_url()
    # Frappe stores this under session.data and materializes it on demand.
    # Reading a nonexistent top-level attribute leaves browser POSTs invalid.
    context.csrf_token = frappe.sessions.get_csrf_token()
