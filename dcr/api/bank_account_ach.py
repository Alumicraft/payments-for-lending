"""
Bank Account ACH Business Logic

Standalone module for ACH-related operations on Bank Account records.
Replaces the ACH Authorization doctype controller logic.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime


def get_customer_default_bank_account(customer):
    """Get the default ACH-enabled Bank Account for a customer.

    Returns the Bank Account doc or None.
    """
    name = frappe.db.get_value(
        "Bank Account",
        {"party_type": "Customer", "party": customer, "is_default": 1, "custom_ach_status": "Active", "disabled": 0},
        "name"
    )
    if name:
        return frappe.get_doc("Bank Account", name)
    return None


def get_loan_payment_account(loan):
    """Get the effective Bank Account for a loan.

    Resolution:
    1. Check loan.ach_payment_account (if active) -> use it
    2. If override exists but not active -> FAIL (don't fall back)
    3. Check customer's default (if active) -> use it
    4. No valid account -> return None
    """
    loan_doc = frappe.get_doc("Loan", loan) if isinstance(loan, str) else loan

    if loan_doc.get("ach_payment_account"):
        ba = frappe.get_doc("Bank Account", loan_doc.ach_payment_account)
        if ba.get("custom_ach_status") == "Active" and not ba.disabled:
            return ba
        else:
            frappe.log_error(
                f"Loan {loan_doc.name} has bank account override {ba.name} but ach_status is {ba.get('custom_ach_status')}, disabled={ba.disabled}",
                "ACH Payment Account Error"
            )
            return None

    return get_customer_default_bank_account(loan_doc.applicant)


def set_as_default(bank_account_name):
    """Set a Bank Account as the default for its customer."""
    ba = frappe.get_doc("Bank Account", bank_account_name)

    if ba.get("custom_ach_status") != "Active":
        frappe.throw(_("Only active bank accounts can be set as default"))

    # Unset other defaults for this customer
    frappe.db.sql("""
        UPDATE `tabBank Account`
        SET is_default = 0
        WHERE party_type = 'Customer' AND party = %s AND is_default = 1 AND name != %s
    """, (ba.party, ba.name))

    ba.is_default = 1
    ba.save()
    return True


def pause(bank_account_name, reason=None):
    """Temporarily pause ACH on a bank account."""
    ba = frappe.get_doc("Bank Account", bank_account_name)

    if ba.get("custom_ach_status") != "Active":
        frappe.throw(_("Only active bank accounts can be paused"))

    ba.custom_ach_status = "Paused"
    if reason:
        ba.add_comment("Comment", f"ACH paused: {reason}")
    ba.save()
    return True


def resume(bank_account_name):
    """Resume ACH on a paused bank account."""
    ba = frappe.get_doc("Bank Account", bank_account_name)

    if ba.get("custom_ach_status") != "Paused":
        frappe.throw(_("Only paused bank accounts can be resumed"))

    ba.custom_ach_status = "Active"
    ba.add_comment("Comment", "ACH resumed")
    ba.save()
    return True


def revoke(bank_account_name, reason=None):
    """Permanently revoke ACH on a bank account and cancel pending transactions."""
    ba = frappe.get_doc("Bank Account", bank_account_name)

    if ba.get("custom_ach_status") == "Revoked":
        frappe.throw(_("Bank account ACH is already revoked"))

    # Warn if this is the only default and customer has active loans
    if ba.is_default:
        other_active = frappe.db.exists(
            "Bank Account",
            {
                "party_type": "Customer",
                "party": ba.party,
                "custom_ach_status": "Active",
                "name": ("!=", ba.name)
            }
        )
        if not other_active:
            loans_using_default = frappe.db.count(
                "Loan",
                {
                    "applicant": ba.party,
                    "status": ["in", ["Disbursed", "Partially Disbursed"]],
                    "ach_payment_account": ["in", ["", None]]
                }
            )
            if loans_using_default > 0:
                frappe.msgprint(
                    _("Warning: {0} active loans will have no payment account after revocation. "
                      "Consider adding a new account first.").format(loans_using_default),
                    indicator="orange"
                )

    ba.custom_ach_status = "Revoked"
    ba.is_default = 0
    ba.disabled = 1
    ba.custom_revocation_date = now_datetime()
    ba.custom_revocation_reason = reason
    ba.save()

    # Cancel pending transactions
    _cancel_pending_transactions(ba.name)

    ba.add_comment("Comment", f"ACH revoked: {reason or 'No reason provided'}")
    return True


def _cancel_pending_transactions(bank_account_name):
    """Cancel all pending ACH transactions for this bank account."""
    pending = frappe.get_all(
        "ACH Transaction",
        filters={
            "bank_account": bank_account_name,
            "status": ["in", ["Scheduled", "Initiated"]]
        },
        pluck="name",
        order_by="creation desc"
    )

    # Also check old ach_authorization field for backward compatibility
    pending_legacy = frappe.get_all(
        "ACH Transaction",
        filters={
            "ach_authorization": bank_account_name,
            "status": ["in", ["Scheduled", "Initiated"]],
            "bank_account": ["in", ["", None]]
        },
        pluck="name",
        order_by="creation desc"
    )

    for txn_name in set(pending + pending_legacy):
        txn = frappe.get_doc("ACH Transaction", txn_name)
        txn.cancel_transaction("Bank account ACH revoked")


def validate_single_default(doc, method):
    """Bank Account validate hook — ensure only one ACH default per customer.

    Only applies to Bank Accounts that have an ach_status field set.
    """
    if not doc.get("custom_ach_status"):
        return

    if doc.is_default and doc.get("custom_ach_status") == "Active":
        existing = frappe.db.exists(
            "Bank Account",
            {
                "party_type": "Customer",
                "party": doc.party,
                "is_default": 1,
                "custom_ach_status": "Active",
                "name": ("!=", doc.name)
            }
        )
        if existing:
            frappe.db.set_value("Bank Account", existing, "is_default", 0)
