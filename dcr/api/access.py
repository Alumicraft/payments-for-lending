"""Authorization for staff APIs; dealer APIs resolve their own customer separately."""
import frappe
from frappe import _


def require_staff(doctype=None, name=None, permission="read"):
    user = frappe.session.user
    if not user or user == "Guest" or frappe.get_cached_value("User", user, "user_type") != "System User":
        frappe.throw(_("This action is only available to staff"), frappe.PermissionError)
    if doctype:
        frappe.has_permission(doctype, permission, doc=name, throw=True)


def visible_chart_records(doctype):
    require_staff(doctype)
    return frappe.get_list(doctype, pluck="name", limit_page_length=0)
