"""Remove the Park DocType from the database.

The Park DocType has been replaced by direct address fields on
Home Build Request. Company data is wiped before this deploy,
so no data migration is needed.
"""
import frappe


def execute():
    if frappe.db.exists("DocType", "Park"):
        frappe.delete_doc("DocType", "Park", force=True)
        frappe.db.commit()
