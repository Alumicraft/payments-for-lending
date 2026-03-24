"""
DCR Email Integration

Sends branded emails via the Vercel react-email service (emails app).
Each function corresponds to one of the 11 DCR email templates.
"""

import frappe
from frappe import _
from frappe.utils import formatdate, fmt_money

from emails.email_service.vercel_client import send_email as vercel_send_email
from emails.email_service.branding import get_company_branding
from emails.email_service.utils import create_communication_log


def _send_dcr_email(
    template,
    to_email,
    subject,
    data,
    reference_doctype=None,
    reference_name=None,
    attachments=None,
    tags=None,
):
    """Internal helper to send a DCR email via the Vercel service.

    Args:
        template: Vercel template name (e.g. "dealer-welcome")
        to_email: Recipient email address
        subject: Email subject line
        data: Template data dict (props for the React component)
        reference_doctype: For communication log linking
        reference_name: For communication log linking
        attachments: List of {"filename": str, "content": base64_str}
        tags: List of {"name": str, "value": str} for Resend tracking

    Returns:
        dict: {"success": True, "message_id": str}
    """
    branding = get_company_branding()

    if not tags:
        tags = []
    tags.append({"name": "app", "value": "dcr"})
    tags.append({"name": "template", "value": template})

    result = vercel_send_email(
        template=template,
        to_email=to_email,
        subject=subject,
        data=data,
        branding=branding,
        attachments=attachments,
        tags=tags,
    )

    message_id = result.get("message_id")

    if reference_doctype and reference_name:
        create_communication_log(
            doctype=reference_doctype,
            docname=reference_name,
            recipient=to_email,
            subject=subject,
            content=result.get("html", f"Sent {template} email"),
            status="Sent",
            message_id=message_id,
        )

    return {"success": True, "message_id": message_id}


# ============================================================================
# 1. ACH Payment Upcoming
# ============================================================================

def send_ach_payment_upcoming(loan, customer_name, scheduled_date, amount, account_last4, to_email, reference_name=None):
    """Send upcoming ACH payment notification."""
    return _send_dcr_email(
        template="ach-payment-upcoming",
        to_email=to_email,
        subject=f"Upcoming Payment — ${amount}",
        data={
            "loan": loan,
            "customer_name": customer_name,
            "scheduled_date": scheduled_date,
            "amount": amount,
            "account_last4": account_last4,
        },
        reference_doctype="Loan",
        reference_name=reference_name or loan,
    )


# ============================================================================
# 2. ACH Payment Success
# ============================================================================

def send_ach_payment_success(loan, customer_name, scheduled_date, amount, to_email, reference_name=None):
    """Send ACH payment success notification."""
    return _send_dcr_email(
        template="ach-payment-success",
        to_email=to_email,
        subject=f"Payment Successful — ${amount}",
        data={
            "loan": loan,
            "customer_name": customer_name,
            "scheduled_date": scheduled_date,
            "amount": amount,
        },
        reference_doctype="Loan",
        reference_name=reference_name or loan,
    )


# ============================================================================
# 3. ACH Payment Failure
# ============================================================================

def send_ach_payment_failure(loan, customer_name, scheduled_date, amount, failure_reason, to_email, reference_name=None):
    """Send ACH payment failure notification."""
    return _send_dcr_email(
        template="ach-payment-failure",
        to_email=to_email,
        subject=f"Payment Failed — ${amount}",
        data={
            "loan": loan,
            "customer_name": customer_name,
            "scheduled_date": scheduled_date,
            "amount": amount,
            "failure_reason": failure_reason,
        },
        reference_doctype="Loan",
        reference_name=reference_name or loan,
    )


# ============================================================================
# 4. Retailer Application
# ============================================================================

def send_retailer_application(customer_name, dealer_license_no, factory_name, to_email, attachments=None, reference_doctype=None, reference_name=None):
    """Send retailer application to factory."""
    return _send_dcr_email(
        template="retailer-application",
        to_email=to_email,
        subject=f"New Dealer Application — {customer_name}",
        data={
            "customer_name": customer_name,
            "dealer_license_no": dealer_license_no,
            "factory_name": factory_name,
        },
        reference_doctype=reference_doctype or "Factory Assignment",
        reference_name=reference_name,
        attachments=attachments,
    )


# ============================================================================
# 5. Dealer Welcome
# ============================================================================

def send_dealer_welcome(customer_name, account_id, to_email, reference_name=None):
    """Send dealer welcome email after account approval."""
    return _send_dcr_email(
        template="dealer-welcome",
        to_email=to_email,
        subject="Welcome to Dealer Capital Resources",
        data={
            "customer_name": customer_name,
            "account_id": account_id,
        },
        reference_doctype="Customer",
        reference_name=reference_name,
    )


# ============================================================================
# 6. Dealer Agreement Sent
# ============================================================================

def send_dealer_agreement_sent(customer_name, email, reference_name=None):
    """Send notification that dealer agreement is ready for signature."""
    return _send_dcr_email(
        template="dealer-agreement-sent",
        to_email=email,
        subject="Dealer Agreement Ready for Signature",
        data={
            "customer_name": customer_name,
            "email": email,
        },
        reference_doctype="Customer",
        reference_name=reference_name,
    )


# ============================================================================
# 7. Dealer Agreement Signed
# ============================================================================

def send_dealer_agreement_signed(customer_name, signed_date, to_email, attachments=None, reference_name=None):
    """Send notification that dealer agreement has been fully executed."""
    return _send_dcr_email(
        template="dealer-agreement-signed",
        to_email=to_email,
        subject="Dealer Agreement Fully Executed",
        data={
            "customer_name": customer_name,
            "signed_date": signed_date,
        },
        reference_doctype="Customer",
        reference_name=reference_name,
        attachments=attachments,
    )


# ============================================================================
# 8. Flooring Packet Sent
# ============================================================================

def send_flooring_packet_sent(customer_name, loan_application, requested_advance_amount, factory_name, to_email, reference_name=None):
    """Send notification that flooring packet is ready for signature."""
    return _send_dcr_email(
        template="flooring-packet-sent",
        to_email=to_email,
        subject="Flooring Packet Ready for Signature",
        data={
            "customer_name": customer_name,
            "loan_application": loan_application,
            "requested_advance_amount": requested_advance_amount,
            "factory_name": factory_name,
        },
        reference_doctype="Loan Application",
        reference_name=reference_name or loan_application,
    )


# ============================================================================
# 9. Flooring Packet Signed
# ============================================================================

def send_flooring_packet_signed(customer_name, loan_application, signed_date, to_email, attachments=None, reference_name=None):
    """Send notification that flooring packet has been fully executed."""
    return _send_dcr_email(
        template="flooring-packet-signed",
        to_email=to_email,
        subject="Flooring Packet Fully Executed",
        data={
            "customer_name": customer_name,
            "loan_application": loan_application,
            "signed_date": signed_date,
        },
        reference_doctype="Loan Application",
        reference_name=reference_name or loan_application,
        attachments=attachments,
    )


# ============================================================================
# 10. Loan Disbursed
# ============================================================================

def send_loan_disbursed(customer_name, factory_name, loan, home_build_request, amount, to_email, reference_name=None):
    """Send notification that loan advance has been disbursed to factory."""
    return _send_dcr_email(
        template="loan-disbursed",
        to_email=to_email,
        subject=f"Loan Advance Disbursed — ${amount}",
        data={
            "customer_name": customer_name,
            "factory_name": factory_name,
            "loan": loan,
            "home_build_request": home_build_request,
            "amount": amount,
        },
        reference_doctype="Loan",
        reference_name=reference_name or loan,
    )


# ============================================================================
# 11. Factory LOA Received
# ============================================================================

def send_factory_loa_received(customer_name, factory_name, loa_date, to_email, reference_name=None):
    """Send notification that factory approval has been received."""
    return _send_dcr_email(
        template="factory-loa-received",
        to_email=to_email,
        subject=f"Factory Approval Received — {factory_name}",
        data={
            "customer_name": customer_name,
            "factory_name": factory_name,
            "loa_date": loa_date,
        },
        reference_doctype="Factory Assignment",
        reference_name=reference_name,
    )


# ============================================================================
# 12. Pre-Approval
# ============================================================================

def send_pre_approval(customer_name, loan_application, loan_amount, to_email, attachments=None, reference_name=None):
    """Send advance pre-approval letter with PDF attachment."""
    return _send_dcr_email(
        template="pre-approval",
        to_email=to_email,
        subject=f"Advance Pre-Approval — {customer_name}",
        data={
            "customer_name": customer_name,
            "loan_application": loan_application,
            "loan_amount": loan_amount,
        },
        attachments=attachments,
        reference_doctype="Loan Application",
        reference_name=reference_name,
    )


# ============================================================================
# 13. Autopay Setup
# ============================================================================

def send_autopay_setup(customer_name, loan_name, loan_amount, setup_url, to_email, reference_name=None):
    """Send email prompting dealer to connect bank account via Plaid."""
    return _send_dcr_email(
        template="autopay-setup",
        to_email=to_email,
        subject=f"Set Up Auto-Pay for Loan {loan_name}",
        data={
            "customer_name": customer_name,
            "loan_name": loan_name,
            "loan_amount": loan_amount,
            "setup_url": setup_url,
        },
        reference_doctype="Loan",
        reference_name=reference_name or loan_name,
    )


# ============================================================================
# 14. Autopay Update
# ============================================================================

def send_autopay_update(customer_name, setup_url, to_email, reference_name=None):
    """Send email prompting dealer to update their bank account via Plaid."""
    return _send_dcr_email(
        template="autopay-update",
        to_email=to_email,
        subject="Update Your Auto-Pay Bank Account",
        data={
            "customer_name": customer_name,
            "setup_url": setup_url,
        },
        reference_doctype="Customer",
        reference_name=reference_name,
    )


@frappe.whitelist()
def send_autopay_update_email(customer):
    """Whitelisted method — send autopay update email to a dealer."""
    customer_doc = frappe.get_doc("Customer", customer)
    customer_doc.check_permission("read")

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer {0} does not have an email address.").format(customer))

    setup_url = frappe.utils.get_url(f"/plaid-setup?customer={customer}")

    send_autopay_update(
        customer_name=customer_doc.customer_name or customer,
        setup_url=setup_url,
        to_email=email,
        reference_name=customer,
    )

    return {"success": True}
