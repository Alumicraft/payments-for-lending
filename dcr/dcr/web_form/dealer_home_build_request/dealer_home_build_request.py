"""DCR branding around the native Frappe Web Form template."""

import frappe

def get_context(context):
    context.dealer_logo = frappe.get_attr("frappe.core.doctype.navbar_settings.navbar_settings.get_app_logo")()
    context.template = "dcr/templates/dealer_hbr.html"
    context.no_cache = 1
    context.title = "Home Build Request"
    if context.get("doc_name"):
        context.title = f"Home Build Request {context.doc_name}"
