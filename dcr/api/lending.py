import frappe
from frappe import _
from frappe.utils import getdate, add_days, today


@frappe.whitelist()
def get_dealer_outstanding_balance(customer):
    """Get total outstanding loan balance for a dealer.

    Pure ERPNext query — no external API.
    """
    result = frappe.db.get_list("Loan",
        filters={
            "applicant": customer,
            "status": ["in", ["Disbursed", "Active"]]
        },
        fields=["sum(outstanding_amount) as total"]
    )
    return result[0].total or 0 if result else 0


@frappe.whitelist()
def get_available_credit(customer):
    """Calculate available credit for a dealer.

    available_credit = MIFA.credit_limit - outstanding_balance
    """
    # Get the most recent MIFA credit limit
    mifa = frappe.db.get_value("MIFA", {"customer": customer},
        "credit_limit", order_by="mifa_date desc")

    if not mifa:
        return {"credit_limit": 0, "outstanding": 0, "available": 0}

    outstanding = get_dealer_outstanding_balance(customer)
    available = mifa - outstanding

    return {
        "credit_limit": mifa,
        "outstanding": outstanding,
        "available": available
    }


def validate_loan_application(doc, method):
    """Hook called on Loan Application validate.

    - Calculates outstanding balance and available credit
    - Validates advance date against factory lead time
    - Warns if requested amount exceeds available credit
    """
    if not doc.get("home_build_request"):
        return

    # Calculate and set balance fields
    customer = doc.applicant
    outstanding = get_dealer_outstanding_balance(customer)
    doc.outstanding_loan_balance = outstanding

    mifa_limit = frappe.db.get_value("MIFA", {"customer": customer},
        "credit_limit", order_by="mifa_date desc")

    if mifa_limit:
        doc.available_credit = mifa_limit - outstanding
    else:
        doc.available_credit = 0

    # Warn if requested amount exceeds available credit
    requested = doc.get("requested_advance_amount") or doc.get("loan_amount") or 0
    if mifa_limit and requested > doc.available_credit:
        frappe.msgprint(
            _("Requested amount {0} exceeds available credit {1} "
              "(Credit limit: {2}, Outstanding: {3})").format(
                frappe.format_value(requested, {"fieldtype": "Currency"}),
                frappe.format_value(doc.available_credit, {"fieldtype": "Currency"}),
                frappe.format_value(mifa_limit, {"fieldtype": "Currency"}),
                frappe.format_value(outstanding, {"fieldtype": "Currency"}),
            ),
            title=_("Credit Limit Warning"),
            indicator="orange"
        )

    # Validate advance date against factory lead time
    if doc.get("advance_date_requested"):
        hbr = frappe.get_doc("Home Build Request", doc.home_build_request)
        if hbr.factory:
            validate_advance_date(hbr.factory, doc.advance_date_requested)


def validate_advance_date(factory, requested_date):
    """Check that requested advance date is achievable given factory lead time.

    Raises a hard error if the date is too soon.
    """
    lead_time = frappe.db.get_value("Supplier", factory, "current_lead_time_days")
    if not lead_time:
        return

    earliest_possible = add_days(today(), lead_time)
    if getdate(requested_date) < getdate(earliest_possible):
        frappe.throw(
            _("Requested advance date {0} is not achievable. "
              "Factory lead time is {1} days — earliest possible date is {2}.").format(
                frappe.format_date(requested_date),
                lead_time,
                frappe.format_date(earliest_possible)
            ),
            title=_("Advance Date Too Early")
        )
