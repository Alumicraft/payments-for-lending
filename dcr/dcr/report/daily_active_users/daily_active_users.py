import frappe
from frappe.utils import add_days, getdate, today


def execute(filters=None):
    columns = [
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 120},
        {"label": "Active Users", "fieldname": "active_users", "fieldtype": "Int", "width": 120},
    ]

    from_date = (filters or {}).get("from_date") or add_days(today(), -30)
    to_date = (filters or {}).get("to_date") or today()

    rows = frappe.db.sql("""
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

    # Build lookup and zero-fill missing days
    counts = {str(row.date): row.active_users for row in rows}
    data = []
    current = getdate(from_date)
    end = getdate(to_date)
    while current <= end:
        date_str = str(current)
        data.append({"date": date_str, "active_users": counts.get(date_str, 0)})
        current = getdate(add_days(current, 1))

    chart = {
        "data": {
            "labels": [row["date"] for row in data],
            "datasets": [{"name": "Active Users", "values": [row["active_users"] for row in data]}],
        },
        "type": "line",
    }

    return columns, data, None, chart
