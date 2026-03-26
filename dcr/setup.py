import frappe


def after_install():
    """Ensure DCR module definition and required groups exist."""
    if not frappe.db.exists("Module Def", "DCR"):
        frappe.get_doc({
            "doctype": "Module Def",
            "module_name": "DCR",
            "app_name": "dcr",
        }).insert(ignore_permissions=True)

    # Supplier Groups
    for group_name in ("Escrow", "Factory"):
        if not frappe.db.exists("Supplier Group", group_name):
            frappe.get_doc({
                "doctype": "Supplier Group",
                "supplier_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Customer Groups
    for group_name in ("Home Buyer", "Dealer"):
        if not frappe.db.exists("Customer Group", group_name):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Clean up removed Custom Fields (fixtures don't auto-delete)
    removed_custom_fields = [
        "Loan Application-dcr_lending_section",
        "Loan Application-requested_advance_amount",
        "Loan Application-column_break_dcr_lending",
        "Loan Application-exhibit_a_section",
        "Loan Application-column_break_exhibit_a",
        "Loan Application-first_autopay_description",
        "Loan Application-custom_projected_investment",
        "Loan Application-dcr_rate_of_interest",
    ]
    for cf_name in removed_custom_fields:
        if frappe.db.exists("Custom Field", cf_name):
            frappe.delete_doc("Custom Field", cf_name, force=True)

    frappe.db.commit()
