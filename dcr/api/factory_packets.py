"""Deliberate staff sending of an assignment's existing retailer packet."""
import frappe
from frappe import _
from dcr.api.access import require_staff


@frappe.whitelist()
def send_packet(name):
    require_staff("Factory Assignment", name, "write")
    require_staff("Factory Assignment", name, "email")
    # Serialize sends against the persisted assignment, not client-supplied fields.
    frappe.db.sql("SELECT name FROM `tabFactory Assignment` WHERE name = %s FOR UPDATE", (name,))
    assignment = frappe.get_doc("Factory Assignment", name)
    if assignment.docstatus != 1 or assignment.retailer_application_status != "Not Submitted":
        frappe.throw(_("Only a submitted assignment with an unsent retailer application can be sent."))
    assignment.send_retailer_application()
    assignment.db_set("retailer_application_status", "Submitted")
