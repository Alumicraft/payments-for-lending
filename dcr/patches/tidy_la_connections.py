import frappe


def execute():
    """Tidy up Loan Application's connections panel.

    - Hide the stock "Loan Security Assignment" link (DCR uses unsecured
      floor-plan loans; the loan_security_details_section is already
      hidden, so the connection card is dead weight).
    - Add a "Lending" group label to the stock "Loan" link so it
      renders with a header matching HBR's connection grouping.
    """
    # Hide Loan Security Assignment connection on Loan Application
    lsa_links = frappe.get_all(
        "DocType Link",
        filters={
            "parent": "Loan Application",
            "parenttype": "DocType",
            "link_doctype": "Loan Security Assignment",
        },
        pluck="name",
    )
    for name in lsa_links:
        frappe.db.set_value("DocType Link", name, "hidden", 1)

    # Group the Loan connection under "Lending"
    loan_links = frappe.get_all(
        "DocType Link",
        filters={
            "parent": "Loan Application",
            "parenttype": "DocType",
            "link_doctype": "Loan",
        },
        pluck="name",
    )
    for name in loan_links:
        frappe.db.set_value("DocType Link", name, "group", "Lending")

    frappe.clear_cache(doctype="Loan Application")
    frappe.db.commit()
