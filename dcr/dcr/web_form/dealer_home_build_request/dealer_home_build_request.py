"""DCR branding around the native Frappe Web Form template."""


def get_context(context):
    context.template = "dcr/templates/dealer_hbr.html"
    context.no_cache = 1
