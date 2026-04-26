import frappe


def execute():
    """Drop the orphan `Loan Application-monthly_interest_amount-hidden`
    Property Setter. The custom field it referenced is being deleted
    via Customize Form, so the setter is no longer meaningful and the
    fixture entry has been removed."""
    name = "Loan Application-monthly_interest_amount-hidden"
    if frappe.db.exists("Property Setter", name):
        frappe.delete_doc("Property Setter", name, force=True)
    frappe.db.commit()
