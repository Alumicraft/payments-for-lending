"""
Plaid Setup Portal Page

Guest-accessible page for dealers to connect their bank account via Plaid.
URL: /plaid-setup?customer=CUST-001&token=XXXX
 or: /plaid-setup?loan=LOAN-001&token=XXXX

Security: HMAC token in URL verified before rendering.
"""

import frappe
import time

no_cache = 1
PLAID_TOKEN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def get_context(context):
    customer = frappe.form_dict.get("customer")
    loan = frappe.form_dict.get("loan")
    token = frappe.form_dict.get("token")

    # Resolve customer from loan if needed
    if loan and not customer:
        customer = frappe.db.get_value("Loan", loan, "applicant")

    if not customer:
        context.error = "Invalid or missing link. Please use the link from your email."
        return

    if not token or not verify_plaid_token(customer, token):
        context.error = "This link has expired or is invalid. Please contact support."
        return

    if not frappe.db.exists("Customer", customer):
        context.error = "Account not found. Please contact support."
        return

    customer_name = frappe.db.get_value("Customer", customer, "customer_name")

    # Check if already connected
    existing = frappe.db.exists("Bank Account", {"party_type": "Customer", "party": customer, "disabled": 0})
    if existing:
        context.already_connected = True
        context.customer_name = customer_name
        return

    # Get Plaid link token
    try:
        from dcr.api.achq_integration import is_plaid_available
        plaid_status = is_plaid_available()
        if not plaid_status.get("available"):
            context.error = "Bank connection is temporarily unavailable. Please try again later."
            return
    except Exception:
        context.error = "Bank connection is temporarily unavailable. Please try again later."
        return

    context.customer = customer
    context.customer_name = customer_name
    context.token = token
    context.show_plaid = True


def generate_plaid_token(customer, issued_at=None):
    """Generate HMAC token for a Plaid setup URL."""
    import hashlib
    import hmac as hmac_mod

    issued_at = int(issued_at if issued_at is not None else time.time())
    secret = frappe.local.conf.get("encryption_key") or frappe.local.conf.get("secret_key")
    signature = hmac_mod.new(
        secret.encode(), f"{customer}:{issued_at}".encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{issued_at}:{signature}"


def verify_plaid_token(customer, token):
    """Verify an HMAC token for a Plaid setup URL."""
    import hashlib
    import hmac as hmac_mod

    try:
        issued_at_raw, signature = (token or "").split(":", 1)
        issued_at = int(issued_at_raw)
    except (TypeError, ValueError):
        return False

    if int(time.time()) - issued_at > PLAID_TOKEN_MAX_AGE_SECONDS:
        return False

    secret = frappe.local.conf.get("encryption_key") or frappe.local.conf.get("secret_key")
    expected = hmac_mod.new(
        secret.encode(), f"{customer}:{issued_at}".encode(), hashlib.sha256
    ).hexdigest()[:32]
    return hmac_mod.compare_digest(signature, expected)
