import frappe


def execute():
    """Populate requirements on submitted HBRs that bypassed an empty checklist."""
    names = frappe.db.sql(
        """
        SELECT hbr.name
        FROM `tabHome Build Request` hbr
        LEFT JOIN `tabDocument Checklist` checklist
          ON checklist.parent = hbr.name
         AND checklist.parenttype = 'Home Build Request'
         AND checklist.parentfield = 'doc_checklist'
        WHERE hbr.docstatus = 1
        GROUP BY hbr.name
        HAVING COUNT(checklist.name) = 0
        """,
        pluck=True,
    )
    for name in names:
        doc = frappe.get_doc("Home Build Request", name)
        doc.ensure_required_checklist()
        if not doc.get("doc_checklist"):
            continue
        doc.flags.ignore_validate_update_after_submit = True
        doc.save(ignore_permissions=True)

    frappe.db.commit()
