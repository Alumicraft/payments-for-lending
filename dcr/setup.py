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

    # Wipe ALL Loan Application custom fields (including manually created ones)
    # Fixture sync recreates them cleanly in chain order
    old_la_fields = frappe.get_all(
        "Custom Field", filters={"dt": "Loan Application"}, pluck="name"
    )
    for cf_name in old_la_fields:
        frappe.delete_doc("Custom Field", cf_name, force=True)

    # Also wipe orphaned Property Setters that may conflict
    old_la_ps = frappe.get_all(
        "Property Setter", filters={"doc_type": "Loan Application"}, pluck="name"
    )
    for ps_name in old_la_ps:
        frappe.delete_doc("Property Setter", ps_name, force=True)

    frappe.db.commit()
