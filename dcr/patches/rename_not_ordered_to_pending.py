"""Rename HBR order stage 'Not Ordered' to 'Pending' on existing rows."""
import frappe


def execute():
    if not frappe.db.has_column("Home Build Request", "custom_order_stage"):
        return

    frappe.db.sql(
        """
        UPDATE `tabHome Build Request`
        SET custom_order_stage = 'Pending'
        WHERE custom_order_stage = 'Not Ordered'
        """
    )
    frappe.db.commit()
