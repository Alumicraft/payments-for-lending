"""
Sales Order Hooks

When a Sales Order for a Floored deal is submitted,
auto-create a Loan Application linked to the Home Build Request.
"""

import frappe
from frappe import _


def on_submit(doc, method):
    """Create Loan Application for Floored deals on Sales Order submit."""
    financing_type = doc.get("financing_type")
    if financing_type != "Floored":
        return

    hbr_name = doc.get("home_build_request")
    if not hbr_name:
        return

    # Don't create duplicate Loan Applications
    existing = frappe.db.exists("Loan Application", {
        "home_build_request": hbr_name,
        "docstatus": ["!=", 2]  # Not cancelled
    })
    if existing:
        frappe.msgprint(
            _("Loan Application {0} already exists for this Home Build Request.").format(existing),
            indicator="orange"
        )
        return

    hbr = frappe.get_doc("Home Build Request", hbr_name)

    la = frappe.new_doc("Loan Application")
    la.applicant_type = "Customer"
    la.applicant = doc.customer
    la.home_build_request = hbr_name
    la.home_type = doc.get("home_type") or hbr.get("home_type")

    # Set loan amount from Sales Order total if available
    if doc.grand_total:
        la.loan_amount = doc.grand_total

    la.insert()

    frappe.msgprint(
        _("Loan Application {0} created for flooring.").format(
            f'<a href="/app/loan-application/{la.name}">{la.name}</a>'
        ),
        indicator="green",
        alert=True,
    )
