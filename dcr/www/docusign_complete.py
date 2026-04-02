"""Landing page after DocuSign signing is complete."""

import frappe

no_cache = 1


def get_context(context):
    event = frappe.form_dict.get("event", "")
    if event == "signing_complete":
        context.title = "Document Signed"
        context.message = "Thank you! Your document has been signed successfully. You can close this page."
        context.icon = "&#10003;"
    elif event == "decline":
        context.title = "Signing Declined"
        context.message = "You have declined to sign this document. Please contact us if you have questions."
        context.icon = "&#10007;"
    else:
        context.title = "Signing Complete"
        context.message = "Thank you! You can close this page."
        context.icon = "&#10003;"
