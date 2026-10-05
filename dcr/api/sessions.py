import frappe
from dcr.api.access import require_staff


@frappe.whitelist()
def get_active_sessions():
    require_staff("User")
    count = frappe.db.sql(
        "SELECT COUNT(DISTINCT user) FROM tabSessions WHERE user != 'Guest'"
    )[0][0]
    return {"value": count, "fieldtype": "Int"}
