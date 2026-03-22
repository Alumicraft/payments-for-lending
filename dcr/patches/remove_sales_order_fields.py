import frappe

def execute():
    """Remove Sales Order custom fields, orphaned Loan fields, and DocType Link."""
    for field in ["Sales Order-home_build_request", "Sales Order-home_type",
                  "Sales Order-financing_type", "Sales Order-property_type",
                  "Loan-rebate_percentage"]:
        if frappe.db.exists("Custom Field", field):
            frappe.delete_doc("Custom Field", field, force=True)

    if frappe.db.exists("DocType Link", "Sales Order-Home Build Request"):
        frappe.delete_doc("DocType Link", "Sales Order-Home Build Request", force=True)

    frappe.db.commit()
