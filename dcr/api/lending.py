import frappe
from frappe import _
from frappe.utils import getdate, add_days, today


@frappe.whitelist()
def get_dealer_outstanding_balance(customer):
    """Get total outstanding loan balance for a dealer.

    Frappe Lending doesn't store an `outstanding_amount` column on Loan;
    the unpaid principal is computed as loan_amount - total_principal_paid.
    """
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(loan_amount - COALESCE(total_principal_paid, 0)), 0) AS total
        FROM `tabLoan`
        WHERE applicant = %s AND status IN ('Disbursed', 'Active')
        """,
        (customer,),
        as_dict=True,
    )
    return result[0].total if result else 0


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
    hbr = None
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

        financing_type = frappe.db.get_value(
            "Home Build Request", doc.home_build_request, "financing_type"
        )
        if financing_type != "Floored":
            frappe.throw(
                _("Loan Applications can only be created for Floored Home Build Requests. "
                  "{0} is {1}.").format(doc.home_build_request, financing_type or _("not marked Floored"))
            )

        hbr = frappe.get_doc("Home Build Request", doc.home_build_request)
        _populate_loan_application_from_hbr(doc, hbr)
    else:
        return

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

    if doc.get("advance_date_requested"):
        if hbr.factory:
            validate_advance_date(hbr.factory, doc.advance_date_requested)

    loan_amount = doc.get("loan_amount") or 0
    sales_price = doc.get("custom_projected_sales_price") or 0
    rate = doc.get("rate_of_interest") or 0
    periods = doc.get("repayment_periods") or 0

    # DCR floor-plan loans are interest-only: dealer pays just the
    # accruing interest each period; principal balloons at payoff.
    # Override Frappe Lending's stock EMI/amortizing calc so the
    # Loan Application preview matches what the actual Loan will use
    # (see dcr/overrides/loan_repayment_schedule.py for the loan-side
    # interest-only schedule).
    if rate and loan_amount:
        monthly_interest = (rate / 100) * loan_amount / 12
        doc.repayment_amount = monthly_interest
        if periods:
            doc.total_payable_interest = monthly_interest * periods
            doc.total_payable_amount = loan_amount + doc.total_payable_interest
        else:
            doc.total_payable_interest = None
            doc.total_payable_amount = None
    else:
        doc.repayment_amount = None
        doc.total_payable_interest = None
        doc.total_payable_amount = None

    # Projected equity / LTV — only meaningful when both inputs are set.
    # Explicitly clear if either becomes empty so a stale calc from a
    # previous save doesn't stick around.
    if loan_amount and sales_price:
        doc.custom_projected_equity = sales_price - loan_amount
        doc.custom_projected_ltv = (loan_amount / sales_price) * 100
    else:
        doc.custom_projected_equity = None
        doc.custom_projected_ltv = None


def _populate_loan_application_from_hbr(doc, hbr):
    """Backfill HBR-derived fields when native connection creation skips fetches."""
    defaults = {
        "applicant_type": "Customer",
        "applicant": hbr.get("customer"),
        "loan_amount": hbr.get("home_invoice_plus_freight"),
        "requested_advance_amount": hbr.get("home_invoice_plus_freight"),
        "buyer_name": hbr.get("home_buyer"),
        "home_serial_no": hbr.get("home_serial_no"),
        "factory": hbr.get("factory"),
        "floor_plan": hbr.get("model_name"),
        "custom_monthly_space_rent": hbr.get("space_rent"),
        "custom_projected_sales_price": hbr.get("selling_price"),
    }
    for fieldname, value in defaults.items():
        if value is not None and not doc.get(fieldname):
            doc.set(fieldname, value)


def validate_advance_date(factory, requested_date):
    """Check that requested advance date is achievable given factory lead time."""
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
    """Populate deal reference fields from Loan Application on every save,
    and block submission if no active bank account is linked.
    """
    _populate_deal_reference(doc)

    # Block submission without bank account
    if doc.docstatus == 1:
        from dcr.api.bank_account_ach import get_loan_payment_account
        account = get_loan_payment_account(doc)
        if not account:
            frappe.throw(
                _("Cannot submit loan: no active bank account is linked for auto-pay. "
                  "The dealer must connect a bank account before this loan can be submitted."),
                title=_("Bank Account Required")
            )


def on_loan_after_insert(doc, method):
    """Auto-link default bank account on Loan creation."""
    if not doc.applicant:
        return

    from dcr.api.bank_account_ach import get_customer_default_bank_account

    existing = get_customer_default_bank_account(doc.applicant)

    if existing:
        bank_name = frappe.db.get_value("Bank", existing.bank, "bank_name") if existing.bank else ""
        doc.db_set("ach_payment_account", existing.name, update_modified=False)
        frappe.msgprint(
            _("Auto-Pay linked to {0} ending in {1}").format(
                bank_name, existing.custom_account_last_four
            ),
            indicator="green",
            alert=True
        )
    else:
        _send_setup_email_if_needed(doc)


def _compute_deal_reference(loan_application, applicant, current=None):
    """Work out what the deal reference fields should be, given the source
    Loan Application and the customer. Returns {field: value} only for fields
    that are currently empty (respecting any manual override on the doc).
    """
    updates = {}
    if not loan_application:
        return updates

    la_fields = frappe.db.get_value(
        "Loan Application", loan_application,
        ["home_build_request", "home_serial_no", "buyer_name", "factory"],
        as_dict=True
    )
    if not la_fields:
        return updates

    current = current or {}

    for field, value in la_fields.items():
        if value and not current.get(field):
            updates[field] = value

    # Fetch rebate percentage from Factory Assignment (dealer + factory pair)
    factory = updates.get("factory") or current.get("factory")
    if factory and applicant and not current.get("custom_rebate_percentage"):
        rebate = frappe.db.get_value(
            "Factory Assignment",
            {"customer": applicant, "factory": factory, "docstatus": 1, "active": 1},
            "rebate_percentage"
        )
        if rebate is not None:
            updates["custom_rebate_percentage"] = rebate

    return updates


def _populate_deal_reference(doc):
    """Server-side: populate deal reference fields on the Loan doc during
    validate. Only fills fields that are currently empty.
    """
    current = {
        "home_build_request": doc.get("home_build_request"),
        "home_serial_no": doc.get("home_serial_no"),
        "buyer_name": doc.get("buyer_name"),
        "factory": doc.get("factory"),
        "custom_rebate_percentage": doc.get("custom_rebate_percentage"),
    }
    for field, value in _compute_deal_reference(
        doc.loan_application, doc.applicant, current
    ).items():
        doc.set(field, value)


@frappe.whitelist()
def get_loan_deal_reference(loan_application, applicant=None):
    """Client-side helper — lets the new-Loan form pre-populate deal
    reference fields the moment it opens (before first save). Mirrors the
    logic run server-side in _populate_deal_reference.
    """
    return _compute_deal_reference(loan_application, applicant)


def on_loan_on_update(doc, method):
    """On every save, check for bank account and auto-send setup email if missing."""
    if not doc.applicant or doc.docstatus != 0:
        return

    from dcr.api.bank_account_ach import get_loan_payment_account

    account = get_loan_payment_account(doc)

    if account:
        # Auto-link if not already set
        if not doc.ach_payment_account:
            doc.db_set("ach_payment_account", account.name, update_modified=False)
        return

    _send_setup_email_if_needed(doc)


def _send_setup_email_if_needed(doc):
    """Send auto-pay setup email if one hasn't been sent in the last 24 hours."""
    # Check if we already sent an email for this loan recently (avoid spam)
    recent_email = frappe.db.exists("Communication", {
        "reference_doctype": "Loan",
        "reference_name": doc.name,
        "subject": ["like", "%Auto-Pay%"],
        "creation": [">=", frappe.utils.add_days(frappe.utils.today(), -1)]
    })

    if recent_email:
        return

    try:
        send_plaid_setup_email(doc)
        frappe.msgprint(
            _("No bank account found for {0}. Auto-pay setup email sent to dealer.").format(
                doc.applicant_name or doc.applicant
            ),
            indicator="green",
            alert=True
        )
    except Exception:
        frappe.log_error("Failed to send auto-pay setup email", "ACH Setup")
        frappe.msgprint(
            _("No bank account linked. Setup email could not be sent — check Error Log."),
            indicator="orange",
            alert=True,
        )


def on_loan_disbursement_validate(doc, method):
    """Populate deal reference fields and block if no bank account."""
    from dcr.api.bank_account_ach import get_loan_payment_account

    loan = frappe.get_doc("Loan", doc.against_loan)

    # Populate HBR and factory from the Loan / HBR chain
    if not doc.home_build_request and loan.get("home_build_request"):
        doc.home_build_request = loan.home_build_request

    if doc.home_build_request and not doc.get("factory"):
        factory = frappe.db.get_value("Home Build Request", doc.home_build_request, "factory")
        if factory:
            doc.factory = factory

    account = get_loan_payment_account(loan)

    if not account:
        frappe.throw(
            _("Cannot disburse loan {0}: no active bank account is linked for auto-pay. "
              "The dealer must connect a bank account before disbursement.").format(doc.against_loan),
            title=_("Bank Account Required")
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

    from dcr.www.plaid_setup import generate_plaid_token
    customer = loan_doc.applicant
    token = generate_plaid_token(customer)
    plaid_setup_url = frappe.utils.get_url(f"/plaid-setup?loan={loan_doc.name}&token={token}")
    loan_amount = frappe.format_value(loan_doc.loan_amount or 0, {"fieldtype": "Currency"}).replace("$", "")

    send_autopay_setup(
        customer_name=loan_doc.applicant_name or loan_doc.applicant,
        loan_name=loan_doc.name,
        loan_amount=loan_amount,
        setup_url=plaid_setup_url,
        to_email=customer_email,
        reference_name=loan_doc.name,
    )
