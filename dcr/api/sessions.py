import frappe


@frappe.whitelist()
def get_active_sessions():
    count = frappe.db.sql(
        "SELECT COUNT(DISTINCT user) FROM tabSessions WHERE user != 'Guest'"
    )[0][0]
    return {"value": count, "fieldtype": "Int"}
