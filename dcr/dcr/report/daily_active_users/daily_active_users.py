import frappe
from frappe.utils import add_days, today


def execute(filters=None):
    columns = [
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 120},
        {"label": "Active Users", "fieldname": "active_users", "fieldtype": "Int", "width": 120},
    ]

    from_date = filters.get("from_date") if filters else add_days(today(), -30)
    to_date = filters.get("to_date") if filters else today()

    data = frappe.db.sql("""
        SELECT
            DATE(creation) as date,
            COUNT(DISTINCT user) as active_users
        FROM `tabActivity Log`
        WHERE operation = 'Login'
          AND DATE(creation) BETWEEN %s AND %s
          AND user != 'Guest'
        GROUP BY DATE(creation)
        ORDER BY DATE(creation)
    """, (from_date, to_date), as_dict=True)

    chart = {
        "data": {
            "labels": [str(row.date) for row in data],
            "datasets": [{"name": "Active Users", "values": [row.active_users for row in data]}],
        },
        "type": "line",
    }

    return columns, data, None, chart
