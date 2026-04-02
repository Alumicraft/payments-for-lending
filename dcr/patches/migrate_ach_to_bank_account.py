"""
Migrate ACH Authorization records to Bank Account.

Idempotent — skips records already migrated (checked via ach_authorization_legacy).

PREREQUISITE: User must create Bank Account custom fields on Frappe Cloud
Customize Form BEFORE deploying this code.
"""

import frappe
from frappe.utils import now_datetime


def execute():
    # Check that custom fields exist on Bank Account
    if not frappe.db.exists("Custom Field", {"dt": "Bank Account", "fieldname": "custom_ach_status"}):
        frappe.log_error(
            "Migration skipped: Bank Account custom field 'custom_ach_status' does not exist. "
            "Create Bank Account custom fields on Frappe Cloud Customize Form first.",
            "ACH Migration"
        )
        return

    authorizations = frappe.db.sql("""
        SELECT name, customer, is_default, status, token_source,
               bank_name, account_type, bank_account_last4, routing_number_last4,
               verification_status, consent_captured, authorization_ip,
               authorization_date, sec_code, revocation_date, revocation_reason
        FROM `tabACH Authorization`
    """, as_dict=True)

    if not authorizations:
        frappe.logger().info("ACH Migration: No ACH Authorization records to migrate")
        return

    # Read tokens separately via SQL since it's a Password field
    tokens = {}
    for row in frappe.db.sql("""
        SELECT name, password as achq_token
        FROM `tabACH Authorization`
    """, as_dict=True):
        tokens[row.name] = row.achq_token

    # Actually, Password fields are stored in __Auth table
    for auth in authorizations:
        token_val = frappe.utils.password.get_decrypted_password(
            "ACH Authorization", auth.name, "achq_token", raise_exception=False
        )
        tokens[auth.name] = token_val

    migrated = 0
    skipped = 0
    auth_to_ba_map = {}  # old ACH Auth name -> new Bank Account name

    for auth in authorizations:
        # Idempotency check
        existing_ba = frappe.db.get_value(
            "Bank Account",
            {"custom_legacy_ach_auth": auth.name},
            "name"
        )
        if existing_ba:
            auth_to_ba_map[auth.name] = existing_ba
            skipped += 1
            continue

        # Find or create Bank record
        bank_record = None
        if auth.bank_name:
            bank_record = frappe.db.get_value("Bank", {"bank_name": auth.bank_name}, "name")
            if not bank_record:
                bank = frappe.new_doc("Bank")
                bank.bank_name = auth.bank_name
                bank.insert(ignore_permissions=True)
                bank_record = bank.name

        # Map status
        ach_status = auth.status  # Active/Paused/Revoked/Failed map directly
        disabled = 1 if auth.status in ("Revoked", "Failed") else 0

        # Create Bank Account
        ba = frappe.new_doc("Bank Account")
        ba.account_name = f"{auth.customer} - {auth.bank_name or 'Bank'} {auth.bank_account_last4}"
        ba.bank = bank_record
        ba.party_type = "Customer"
        ba.party = auth.customer
        ba.is_default = auth.is_default
        ba.is_company_account = 0
        ba.disabled = disabled

        # ACH custom fields
        ba.custom_ach_status = ach_status
        ba.custom_achq_token = tokens.get(auth.name, "")
        ba.custom_token_source = auth.token_source
        ba.custom_account_last_four = auth.bank_account_last4
        ba.custom_routing_last_four = auth.routing_number_last4
        ba.custom_verification_status = auth.verification_status
        ba.custom_consent_captured = auth.consent_captured
        ba.custom_authorization_ip = auth.authorization_ip
        ba.custom_authorization_date = auth.authorization_date
        ba.custom_sec_code = auth.sec_code
        ba.custom_revocation_date = auth.revocation_date
        ba.custom_revocation_reason = auth.revocation_reason
        ba.custom_legacy_ach_auth = auth.name

        ba.flags.ignore_validate = True  # Skip validate hook during migration
        ba.insert(ignore_permissions=True)

        auth_to_ba_map[auth.name] = ba.name
        migrated += 1

    # Update Loan records — change ach_payment_account from ACH Auth names to Bank Account names
    loans_updated = 0
    loans_with_ach = frappe.db.sql("""
        SELECT name, ach_payment_account
        FROM `tabLoan`
        WHERE ach_payment_account IS NOT NULL AND ach_payment_account != ''
    """, as_dict=True)

    for loan in loans_with_ach:
        new_ba = auth_to_ba_map.get(loan.ach_payment_account)
        if new_ba:
            frappe.db.set_value("Loan", loan.name, "ach_payment_account", new_ba, update_modified=False)
            loans_updated += 1

    # Update ACH Transaction records — populate bank_account field
    txns_updated = 0
    txns_with_auth = frappe.db.sql("""
        SELECT name, ach_authorization
        FROM `tabACH Transaction`
        WHERE ach_authorization IS NOT NULL AND ach_authorization != ''
    """, as_dict=True)

    for txn in txns_with_auth:
        new_ba = auth_to_ba_map.get(txn.ach_authorization)
        if new_ba:
            frappe.db.set_value("ACH Transaction", txn.name, "bank_account", new_ba, update_modified=False)
            txns_updated += 1

    frappe.db.commit()

    summary = (
        f"ACH Migration complete: "
        f"{migrated} authorizations migrated, {skipped} already migrated, "
        f"{loans_updated} loans updated, {txns_updated} transactions updated"
    )
    frappe.logger().info(summary)
    print(summary)
