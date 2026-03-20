import frappe


def execute():
    """Rename 'DCR Floored' to 'Floored' in all affected doctypes."""
    # Table names are hardcoded constants, not user input
    for dt in ("Home Build Request", "Sales Order"):
        frappe.db.sql(
            """UPDATE `tab{dt}` SET financing_type = 'Floored'
            WHERE financing_type = 'DCR Floored'""".format(dt=dt)
        )
    frappe.db.commit()
