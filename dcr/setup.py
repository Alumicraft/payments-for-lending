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

    # Delete known orphaned custom fields (manually created or removed from fixtures)
    orphans = [
        "Loan Application-requested_advance_amount",
        "Loan Application-column_break_dcr_lending",
        "Loan Application-exhibit_a_section",
        "Loan Application-column_break_exhibit_a",
        "Loan Application-first_autopay_description",
        "Loan Application-custom_projected_investment",
    ]
    for cf_name in orphans:
        if frappe.db.exists("Custom Field", cf_name):
            frappe.delete_doc("Custom Field", cf_name, force=True)

    # Delete manually created fields that conflict with fixtures
    manual_fields = frappe.get_all(
        "Custom Field",
        filters={"dt": "Loan Application", "name": ["like", "Loan Application-custom_column_break_%"]},
        pluck="name"
    )
    for cf_name in manual_fields:
        frappe.delete_doc("Custom Field", cf_name, force=True)
    if frappe.db.exists("Custom Field", "Loan Application-custom_lending_overview"):
        frappe.delete_doc("Custom Field", "Loan Application-custom_lending_overview", force=True)

    frappe.db.commit()
