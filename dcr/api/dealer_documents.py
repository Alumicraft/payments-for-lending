"""Safe dealer-document field updates after Frappe file uploads."""

import frappe
from frappe import _


DEALER_DOCUMENT_FIELDS = frozenset({
    "dealer_license_copy",
    "sellers_permit_copy",
    "w9_copy",
    "retailer_application_copy",
})


@frappe.whitelist()
def set_dealer_document(customer, fieldname, file_url):
    """Persist one uploaded dealer document without saving a stale browser doc.

    Frappe's upload endpoint adds an Attachment comment to the Customer before
    the Attach control saves its field. Loading the Customer again here gives
    this write the new ``modified`` value while limiting the change to the
    requested document field.
    """
    if fieldname not in DEALER_DOCUMENT_FIELDS:
        frappe.throw(_("Unsupported dealer document field"))

    customer_doc = frappe.get_doc("Customer", customer)
    customer_doc.check_permission("write")
    if customer_doc.customer_group != "Dealer":
        frappe.throw(_("Dealer documents can only be added to Dealer customers"))

    attached_file = frappe.db.exists(
        "File",
        {
            "file_url": file_url,
            "attached_to_doctype": "Customer",
            "attached_to_name": customer,
            "attached_to_field": fieldname,
        },
    )
    if not attached_file:
        frappe.throw(_("The uploaded file is not attached to this dealer document field"))

    customer_doc.set(fieldname, file_url)
    customer_doc.save()

    return {
        "file_url": file_url,
        "modified": str(customer_doc.modified),
    }
