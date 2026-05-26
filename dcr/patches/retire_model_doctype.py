"""Replace HBR Link-to-Model with a plain-text floor_plan field.

The Model doctype was a thin link-target only used to fetch the manufacturer
onto the HBR factory field. It's been retired in favor of a free-text
floor_plan column and a user-entered factory link.
"""
import frappe
from frappe.model.rename_field import rename_field


def execute():
    if frappe.db.has_column("Home Build Request", "model_name") and not frappe.db.has_column(
        "Home Build Request", "floor_plan"
    ):
        rename_field("Home Build Request", "model_name", "floor_plan")

    if frappe.db.exists("DocType", "Model"):
        frappe.delete_doc("DocType", "Model", force=True, ignore_missing=True)

    frappe.db.commit()
