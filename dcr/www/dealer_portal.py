"""Dealer portal website page."""

import frappe


no_cache = 1


def get_context(context):
    context.title = "Dealer Portal"
    context.portal_user = frappe.session.user
    context.is_guest = frappe.session.user in (None, "Guest", "guest")
    context.login_url = "/login?redirect-to=/portal"
    context.csrf_token = getattr(frappe.session, "csrf_token", "")
