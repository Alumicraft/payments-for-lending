"""DCR branding around the native Frappe Web Form template."""


def get_context(context):
    from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo
    context.dealer_logo = get_app_logo()
    context.template = "dcr/templates/dealer_hbr.html"
    context.no_cache = 1
    context.title = "Home Build Request"
    if context.get("doc_name"):
        context.title = f"Home Build Request {context.doc_name}"
