import frappe


def execute():
    """Backfill the legacy HBR status field from docstatus."""
    frappe.db.sql(
        """
        UPDATE `tabHome Build Request`
        SET status = 'Submitted'
        WHERE docstatus = 1
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabHome Build Request`
        SET status = 'Draft'
        WHERE docstatus = 0
        """
    )
