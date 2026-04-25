import frappe


def execute():
    """Drop the old `-default = 0` property setters on three calculated LA
    fields. The new `-placeholder = 0.00` setters get re-created from
    fixtures on the next migrate. Leaving the stale `-default` entries
    in place would override the placeholder behavior."""
    for name in [
        "Loan Application-repayment_amount-default",
        "Loan Application-total_payable_amount-default",
        "Loan Application-total_payable_interest-default",
    ]:
        if frappe.db.exists("Property Setter", name):
            frappe.delete_doc("Property Setter", name, force=True)

    frappe.db.commit()
