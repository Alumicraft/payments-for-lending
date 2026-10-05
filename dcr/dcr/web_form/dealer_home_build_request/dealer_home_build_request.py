"""DCR branding around the native Frappe Web Form template."""


def get_context(context):
    context.template = "dcr/templates/dealer_hbr.html"
    context.no_cache = 1
    context.title = "Home Build Request"
    if context.get("doc_name"):
        context.title = f"Home Build Request {context.doc_name}"
