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


def is_dealer_current(customer):
    """Check if a dealer has any overdue (unpaid + past due) loan repayment entries.

    Returns "Yes" if no overdue payments, "No" if any exist.
    """
    overdue = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabRepayment Schedule` rs
        INNER JOIN `tabLoan` l ON rs.parent = l.name
        WHERE l.applicant = %s
        AND l.status IN ('Disbursed', 'Active')
        AND rs.payment_date < %s
        AND rs.demand_generated = 0
    """, (customer, today()))[0][0]

    return "Yes" if overdue == 0 else "No"


@frappe.whitelist()
def get_available_credit(customer):
    """Calculate available credit for a dealer.

    available_credit = MIFA.credit_limit - outstanding_balance
    """
    # Get the most recent MIFA credit limit
    mifa = frappe.db.get_value("MIFA", {"customer": customer, "docstatus": 1},
        "credit_limit", order_by="mifa_date desc")

    if not mifa:
        return {"credit_limit": 0, "outstanding": 0, "available": 0}

    outstanding = get_dealer_outstanding_balance(customer)
    available = mifa - outstanding

    return {
        "credit_limit": mifa,
        "outstanding": outstanding,
        "available": available,
        "current_yn": is_dealer_current(customer)
    }


def validate_loan_application(doc, method):
    """Hook called on Loan Application validate.

    - Ensures linked HBR is submitted
    - Calculates outstanding balance and available credit
    - Validates advance date against factory lead time
    - Warns if requested amount exceeds available credit
    """
    # Ensure linked HBR is submitted
    if doc.get("home_build_request"):
        hbr_status = frappe.db.get_value(
            "Home Build Request", doc.home_build_request, "docstatus"
        )
        if hbr_status != 1:
            frappe.throw(
                _("Home Build Request {0} must be submitted before linking to a Loan Application.").format(
                    doc.home_build_request
                )
            )
    else:
        return

    # Calculate and set balance fields
    customer = doc.applicant
    doc.custom_current_yn = is_dealer_current(customer)
    outstanding = get_dealer_outstanding_balance(customer)
    doc.outstanding_loan_balance = outstanding

    mifa_limit = frappe.db.get_value("MIFA", {"customer": customer, "docstatus": 1},
        "credit_limit", order_by="mifa_date desc")

    if mifa_limit:
        doc.available_credit = mifa_limit - outstanding
    else:
        doc.available_credit = 0

    # Warn if requested amount exceeds available credit
    requested = doc.get("loan_amount") or 0
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

    # Auto-calculate pre-approval fields
    loan_amount = doc.get("loan_amount") or 0
    sales_price = doc.get("custom_projected_sales_price") or 0

    if loan_amount and sales_price:
        doc.custom_projected_equity = sales_price - loan_amount
        doc.custom_projected_ltv = (loan_amount / sales_price) * 100


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


def on_loan_validate(doc, method):
    """Populate home_build_request from Loan Application.

    Other deal reference fields (home_serial_no, buyer_name, factory)
    are handled by fetch_from declarations in fixtures.
    """
    if not doc.loan_application:
        return
    if not doc.home_build_request:
        hbr = frappe.db.get_value(
            "Loan Application", doc.loan_application, "home_build_request"
        )
        if hbr:
            doc.home_build_request = hbr


def on_loan_after_insert(doc, method):
    """Auto-link ACH payment account or send Plaid setup email on loan creation."""
    if not doc.applicant:
        return

    # Check for existing ACH Authorization on this customer
    existing_auth = frappe.db.get_value(
        "ACH Authorization",
        {"customer": doc.applicant, "status": "Active", "is_default": 1},
        ["name", "bank_name", "bank_account_last4"],
        as_dict=True
    )

    if existing_auth:
        doc.db_set("ach_payment_account", existing_auth.name, update_modified=False)
        frappe.msgprint(
            _("Auto-Pay linked to {0} ending in {1}").format(
                existing_auth.bank_name, existing_auth.bank_account_last4
            ),
            indicator="green",
            alert=True
        )
    else:
        try:
            send_plaid_setup_email(doc)
        except Exception:
            frappe.log_error("Failed to send Plaid setup email", "ACH Setup")
            frappe.msgprint(
                _("Loan created but auto-pay setup email could not be sent. Check Error Log."),
                indicator="orange",
                alert=True,
            )


def send_plaid_setup_email(loan_doc):
    """Send dealer an email to connect their bank account via Plaid."""
    customer_email = frappe.db.get_value("Customer", loan_doc.applicant, "email_id")
    if not customer_email:
        frappe.log_error(
            f"Cannot send Plaid setup email: no email on Customer {loan_doc.applicant}",
            "ACH Setup"
        )
        return

    from dcr.api.dcr_email import send_autopay_setup

    plaid_setup_url = frappe.utils.get_url(f"/plaid-setup?loan={loan_doc.name}")
    loan_amount = frappe.format_value(loan_doc.loan_amount or 0, {"fieldtype": "Currency"}).replace("$", "")

    send_autopay_setup(
        customer_name=loan_doc.applicant_name or loan_doc.applicant,
        loan_name=loan_doc.name,
        loan_amount=loan_amount,
        setup_url=plaid_setup_url,
        to_email=customer_email,
        reference_name=loan_doc.name,
    )
