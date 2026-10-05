"""Dealer portal website page."""

import frappe


no_cache = 1


def get_context(context):
    if frappe.session.user in (None, "Guest", "guest"):
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    context.title = "Dealer Portal"
    context.portal_user = frappe.session.user
    # Frappe stores this under session.data and materializes it on demand.
    # Reading a nonexistent top-level attribute leaves browser POSTs invalid.
    context.csrf_token = frappe.sessions.get_csrf_token()
