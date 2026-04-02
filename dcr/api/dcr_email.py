"""
DCR Email Integration

Sends branded emails via the emails app generic pipeline.
Each function passes template-specific data via extra_data override.
"""

import frappe
from frappe import _


def _send(
    doctype,
    docname,
    to_email,
    subject,
    template,
    extra_data=None,
    attachments=None,
    cc=None,
):
    """Internal helper — routes through the emails app generic pipeline."""
    from emails.email_service.generic_email import send_document_email

    return send_document_email(
        doctype=doctype,
        docname=docname,
        to_email=to_email,
        subject_override=subject,
        template_override=template,
        extra_data=extra_data,
        attachments=attachments or [],
        cc=cc,
    )


# ============================================================================
# 1. ACH Payment Upcoming
# ============================================================================

def send_ach_payment_upcoming(loan, customer_name, scheduled_date, amount, account_last4, to_email, reference_name=None):
    """Send upcoming ACH payment notification."""
    return _send(
        doctype="Loan",
        docname=reference_name or loan,
        to_email=to_email,
        subject=f"Upcoming Payment — ${amount}",
        template="ach-payment-upcoming",
        extra_data={
            "loan": loan,
            "customer_name": customer_name,
            "scheduled_date": scheduled_date,
            "amount": amount,
            "account_last4": account_last4,
        },
    )


# ============================================================================
# 2. ACH Payment Success
# ============================================================================

def send_ach_payment_success(loan, customer_name, scheduled_date, amount, to_email, reference_name=None):
    """Send ACH payment success notification."""
    return _send(
        doctype="Loan",
        docname=reference_name or loan,
        to_email=to_email,
        subject=f"Payment Successful — ${amount}",
        template="ach-payment-success",
        extra_data={
            "loan": loan,
            "customer_name": customer_name,
            "scheduled_date": scheduled_date,
            "amount": amount,
        },
    )


# ============================================================================
# 3. ACH Payment Failure
# ============================================================================

def send_ach_payment_failure(loan, customer_name, scheduled_date, amount, failure_reason, to_email, reference_name=None):
    """Send ACH payment failure notification."""
    return _send(
        doctype="Loan",
        docname=reference_name or loan,
        to_email=to_email,
        subject=f"Payment Failed — ${amount}",
        template="ach-payment-failure",
        extra_data={
            "loan": loan,
            "customer_name": customer_name,
            "scheduled_date": scheduled_date,
            "amount": amount,
            "failure_reason": failure_reason,
        },
    )


# ============================================================================
# 4. Retailer Application
# ============================================================================

def send_retailer_application(customer_name, dealer_license_no, factory_name, to_email, attachments=None, reference_doctype=None, reference_name=None):
    """Send retailer application to factory."""
    return _send(
        doctype=reference_doctype or "Factory Assignment",
        docname=reference_name,
        to_email=to_email,
        subject=f"New Dealer Application — {customer_name}",
        template="retailer-application",
        extra_data={
            "customer_name": customer_name,
            "dealer_license_no": dealer_license_no,
            "factory_name": factory_name,
        },
        attachments=attachments,
    )


# ============================================================================
# 5. Dealer Welcome
# ============================================================================

def send_dealer_welcome(customer_name, account_id, to_email, reference_name=None):
    """Send dealer welcome email after account approval."""
    return _send(
        doctype="Customer",
        docname=reference_name or account_id,
        to_email=to_email,
        subject="Welcome to Dealer Capital Resources",
        template="dealer-welcome",
        extra_data={
            "customer_name": customer_name,
            "dcr_account_no": account_id,
        },
    )


# ============================================================================
# 6. Dealer Agreement Sent
# ============================================================================

def send_dealer_agreement_sent(customer_name, email, reference_name=None):
    """Send notification that dealer agreement is ready for signature."""
    return _send(
        doctype="Customer",
        docname=reference_name,
        to_email=email,
        subject="Dealer Agreement Ready for Signature",
        template="dealer-agreement-sent",
        extra_data={
            "customer_name": customer_name,
            "email": email,
        },
    )


# ============================================================================
# 7. Dealer Agreement Signed
# ============================================================================

def send_dealer_agreement_signed(customer_name, signed_date, to_email, attachments=None, reference_name=None):
    """Send notification that dealer agreement has been fully executed."""
    return _send(
        doctype="Customer",
        docname=reference_name,
        to_email=to_email,
        subject="Dealer Agreement Fully Executed",
        template="dealer-agreement-signed",
        extra_data={
            "customer_name": customer_name,
            "signed_date": signed_date,
        },
        attachments=attachments,
    )


# ============================================================================
# 8. Flooring Packet Sent
# ============================================================================

def send_flooring_packet_sent(customer_name, loan_application, loan_amount, factory_name, to_email, reference_name=None):
    """Send notification that flooring packet is ready for signature."""
    return _send(
        doctype="Loan Application",
        docname=reference_name or loan_application,
        to_email=to_email,
        subject="Flooring Packet Ready for Signature",
        template="flooring-packet-sent",
        extra_data={
            "customer_name": customer_name,
            "loan_application": loan_application,
            "loan_amount": loan_amount,
            "factory_name": factory_name,
        },
    )


# ============================================================================
# 9. Flooring Packet Signed
# ============================================================================

def send_flooring_packet_signed(customer_name, loan_application, signed_date, to_email, attachments=None, reference_name=None):
    """Send notification that flooring packet has been fully executed."""
    return _send(
        doctype="Loan Application",
        docname=reference_name or loan_application,
        to_email=to_email,
        subject="Flooring Packet Fully Executed",
        template="flooring-packet-signed",
        extra_data={
            "customer_name": customer_name,
            "loan_application": loan_application,
            "signed_date": signed_date,
        },
        attachments=attachments,
    )


# ============================================================================
# 10. Loan Disbursed
# ============================================================================

def send_loan_disbursed(customer_name, factory_name, loan, home_build_request, amount, to_email, reference_name=None):
    """Send notification that loan advance has been disbursed to factory."""
    return _send(
        doctype="Loan",
        docname=reference_name or loan,
        to_email=to_email,
        subject=f"Loan Advance Disbursed — ${amount}",
        template="loan-disbursed",
        extra_data={
            "customer_name": customer_name,
            "factory_name": factory_name,
            "loan": loan,
            "home_build_request": home_build_request,
            "amount": amount,
        },
    )


# ============================================================================
# 11. Factory LOA Received
# ============================================================================

def send_factory_loa_received(customer_name, factory_name, loa_date, to_email, reference_name=None):
    """Send notification that factory approval has been received."""
    return _send(
        doctype="Factory Assignment",
        docname=reference_name,
        to_email=to_email,
        subject=f"Factory Approval Received — {factory_name}",
        template="factory-loa-received",
        extra_data={
            "customer_name": customer_name,
            "factory_name": factory_name,
            "loa_date": loa_date,
        },
    )


# ============================================================================
# 12. Pre-Approval
# ============================================================================

def send_pre_approval(customer_name, loan_application, loan_amount, to_email, attachments=None, reference_name=None):
    """Send advance pre-approval letter with PDF attachment."""
    return _send(
        doctype="Loan Application",
        docname=reference_name or loan_application,
        to_email=to_email,
        subject=f"Advance Pre-Approval — {customer_name}",
        template="pre-approval",
        extra_data={
            "customer_name": customer_name,
            "loan_application": loan_application,
            "loan_amount": loan_amount,
        },
        attachments=attachments,
    )


# ============================================================================
# 13. Autopay Setup
# ============================================================================

def send_autopay_setup(customer_name, loan_name, loan_amount, setup_url, to_email, reference_name=None):
    """Send email prompting dealer to connect bank account via Plaid."""
    return _send(
        doctype="Loan",
        docname=reference_name or loan_name,
        to_email=to_email,
        subject=f"Set Up Auto-Pay for Loan {loan_name}",
        template="autopay-setup",
        extra_data={
            "customer_name": customer_name,
            "loan_name": loan_name,
            "loan_amount": loan_amount,
            "setup_url": setup_url,
        },
    )


# ============================================================================
# 14. Autopay Update
# ============================================================================

def send_autopay_update(customer_name, setup_url, to_email, reference_name=None):
    """Send email prompting dealer to update their bank account via Plaid."""
    return _send(
        doctype="Customer",
        docname=reference_name,
        to_email=to_email,
        subject="Update Your Auto-Pay Bank Account",
        template="autopay-update",
        extra_data={
            "customer_name": customer_name,
            "setup_url": setup_url,
        },
    )


# ============================================================================
# 15. Autopay Connected Confirmation
# ============================================================================

def send_autopay_connected(customer_name, bank_name, account_last4, to_email, reference_name=None):
    """Send confirmation that bank account has been successfully connected for auto-pay."""
    return _send(
        doctype="Customer",
        docname=reference_name,
        to_email=to_email,
        subject="Auto-Pay Bank Account Connected",
        template="autopay-connected",
        extra_data={
            "customer_name": customer_name,
            "bank_name": bank_name,
            "account_last4": account_last4,
        },
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
