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

    # Workspaces — deploys/migrations can delete these; ensure they exist.
    for ws in ("Overview", "Deals", "Accounting", "Contacts", "Access"):
        if not frappe.db.exists("Workspace", ws):
            frappe.get_doc({
                "doctype": "Workspace",
                "label": ws,
                "title": ws,
                "public": 1,
                "module": "DCR",
            }).insert(ignore_permissions=True)

    # Number Card: Users Online
    card_name = "Users Online"
    if not frappe.db.exists("Number Card", card_name):
        frappe.get_doc({
            "doctype": "Number Card",
            "name": card_name,
            "label": card_name,
            "type": "Custom",
            "method": "dcr.api.sessions.get_active_sessions",
            "is_public": 1,
            "owner": "Administrator",
        }).insert(ignore_permissions=True)

    # Dashboard Chart: Active Users Per Day
    chart_name = "Active Users Per Day"
    if not frappe.db.exists("Dashboard Chart", chart_name):
        frappe.get_doc({
            "doctype": "Dashboard Chart",
            "chart_name": chart_name,
            "chart_type": "Report",
            "report_name": "Daily Active Users",
            "type": "Line",
            "is_public": 1,
            "owner": "Administrator",
        }).insert(ignore_permissions=True)

    # Ensure Number Card + Chart are on the Access workspace
    access_ws = frappe.get_doc("Workspace", "Access")
    changed = False

    card_linked = any(
        row.number_card_name == card_name
        for row in access_ws.get("number_cards", [])
    )
    if not card_linked:
        access_ws.append("number_cards", {"number_card_name": card_name})
        changed = True

    chart_linked = any(
        row.chart_name == chart_name
        for row in access_ws.get("charts", [])
    )
    if not chart_linked:
        access_ws.append("charts", {"chart_name": chart_name})
        changed = True

    if changed:
        access_ws.save(ignore_permissions=True)

    frappe.db.commit()
