import frappe

def execute():
    """Hide irrelevant Lending module fields and sections from DCR forms."""
    fields_to_hide = [
        "Customer-loan_details_tab",
    ]

    for field_name in fields_to_hide:
        if frappe.db.exists("Custom Field", field_name):
            frappe.db.set_value("Custom Field", field_name, "hidden", 1)

    frappe.db.commit()
