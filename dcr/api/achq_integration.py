# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
ACHQ Integration Module

Provides client for ACHQ API operations and webhook handling.
Based on ACHQ API documentation at developers.achq.com
"""

import csv
import hashlib
import hmac
import io
import json
from contextlib import contextmanager

import frappe
from dcr.api.access import require_staff
from frappe import _
from frappe.utils import now_datetime, getdate, today
import requests


# ACHQ Status to internal status mapping
ACHQ_STATUS_MAP = {
    "Scheduled": "Scheduled",
    "InProcess": "Processing",
    "Cleared": "Success",
    "Settled": "Success",
    "Returned": "Returned",
    "Returned-NSF": "Returned",
    "Returned-Other": "Returned",
    "ChargedBack": "Returned",
    "Cancelled": "Cancelled",
    "Rejected": "Failed",
}


class ACHQClient:
    """Client for ACHQ API operations using Direct Merchant mode."""

    BASE_URL = "https://www.speedchex.com/datalinks/transact.aspx"

    def __init__(self, allow_disabled=False):
        self.allow_disabled = allow_disabled
        self.settings = frappe.get_single("ACH Settings")
        self._validate_settings()

    def _validate_settings(self):
        """Validate that required settings are configured."""
        if not self.settings.enable_ach_autopay and not self.allow_disabled:
            frappe.throw(_("ACH Autopay is not enabled"))

    def _get_auth_params(self):
        """Get authentication parameters for Direct Merchant mode."""
        params = {
            "MerchantID": self.settings.achq_merchant_id,
            "Merchant_GateID": self.settings.achq_merchant_gate_id,
            "Merchant_GateKey": self.settings.get_password("achq_merchant_gate_key"),
        }

        if self.settings.achq_environment == "Public Sandbox" and params != {
            "MerchantID": "2001", "Merchant_GateID": "test", "Merchant_GateKey": "test"
        }:
            frappe.throw(_("Public Sandbox requires the published 2001/test/test credentials"))

        # Add TestMode for sandbox
        if self.settings.achq_environment == "Sandbox":
            params["TestMode"] = "On"

        return params

    def _make_request(self, command, params, response_parser=None):
        """Make a request to ACHQ API."""
        data = self._get_auth_params()
        data["Command"] = command
        data["CommandVersion"] = "2.0"
        data["ResponseType"] = "JSON"
        data.update(params)

        try:
            response = requests.post(self.BASE_URL, data=data, timeout=30)
            response.raise_for_status()
            return (response_parser or self._parse_response)(response.text)
        except requests.RequestException as e:
            frappe.log_error(
                f"ACHQ API request failed: {str(e)}",
                "ACHQ Integration"
            )
            return {"success": False, "outcome_unknown": True, "error_message": str(e)}

    # Expected top-level keys in valid ACHQ responses
    _VALID_RESPONSE_KEYS = {
        "CommandStatus", "ResponseCode", "Description", "ErrorInformation",
        "TransactionID", "TransAct_ReferenceID", "Transact_ReferenceID", "Provider_TransactionID",
        "ResponseData", "ACHQToken", "BankName",
        "ExpressVerify", "PaymentStatus", "Transactions",
    }

    def _parse_response(self, response_text):
        """Parse and validate ACHQ JSON response."""
        if not response_text:
            return {"success": False, "outcome_unknown": True, "error_message": "Empty response"}

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            frappe.log_error(
                f"ACHQ response JSON parse error: {str(e)}",
                "ACHQ Integration"
            )
            return {"success": False, "outcome_unknown": True, "error_message": f"Invalid JSON response: {str(e)}"}

        # Basic schema validation — must be a dict with expected keys
        if not isinstance(result, dict):
            frappe.log_error(
                f"ACHQ response is not a JSON object: {type(result).__name__}",
                "ACHQ Integration"
            )
            return {"success": False, "outcome_unknown": True, "error_message": "Invalid response format"}

        # Warn if response contains unexpected keys (possible tampering)
        unexpected = set(result.keys()) - self._VALID_RESPONSE_KEYS
        if unexpected:
            frappe.logger().warning(
                f"ACHQ response contains unexpected keys: {unexpected}"
            )

        # Check for success based on CommandStatus
        command_status = str(result.get("CommandStatus", "")).lower()
        response_code = str(result.get("ResponseCode", ""))

        if (command_status == "approved" and response_code in ("", "000")) or (not command_status and response_code == "000"):
            result["success"] = True
        else:
            result["success"] = False
            result["error_message"] = result.get("Description",
                result.get("ErrorInformation", {}).get("Message", "Unknown error")
                if isinstance(result.get("ErrorInformation"), dict)
                else result.get("ErrorInformation", "Unknown error")
            )
            result["error_code"] = response_code
            result["outcome_unknown"] = not bool(command_status in ("declined", "rejected", "error") or response_code not in ("", "000"))

        return result

    def tokenize_and_verify(self, routing_number, account_number, account_type, customer_name, check_type=None):
        """
        Create a token and verify the bank account.

        Args:
            routing_number: 9-digit routing number
            account_number: Bank account number
            account_type: 'Checking' or 'Savings'
            customer_name: Customer's name for the account
            check_type: 'Personal' or 'Business' (defaults to settings)

        Returns:
            dict with success, token, bank_name, verify_status
        """
        params = {
            "RoutingNumber": routing_number,
            "AccountNumber": account_number,
            "AccountType": account_type,
            "CheckType": check_type or self.settings.default_check_type or "Business",
        }

        # Add Express Verify if enabled
        if self.settings.use_express_verify:
            params["Run_ExpressVerify"] = "Yes"

        result = self._make_request("ECheck.CreateACHQToken", params)

        if result.get("success"):
            # Handle nested ExpressVerify response
            express_verify = result.get("ExpressVerify", {})
            if isinstance(express_verify, dict):
                verify_status = express_verify.get("Status", "UNK")
                verify_code = express_verify.get("Code")
                verify_desc = express_verify.get("Description")
            else:
                verify_status = "UNK"
                verify_code = None
                verify_desc = None

            return {
                "success": True,
                "token": result.get("ACHQToken"),
                "bank_name": result.get("BankName", ""),
                "verify_status": verify_status,
                "verify_code": verify_code,
                "verify_description": verify_desc,
                "routing_last4": routing_number[-4:] if len(routing_number) >= 4 else routing_number,
                "account_last4": account_number[-4:] if len(account_number) >= 4 else account_number,
                "transact_reference_id": result.get("TransAct_ReferenceID"),
            }

        return result

    def payment_parameters(self, amount, token, customer_name, description, txn_id,
                           customer_ip=None, token_source=None, billing=None):
        """Validate every required token-payment field before durable admission."""
        billing = billing or {}
        if self.settings.achq_environment == "Public Sandbox" and self.settings.ach_scope != "Controlled Pilot":
            frappe.throw(_("Public Sandbox payments require Controlled Pilot scope and fabricated data"))
        required = ("Billing_Address1", "Billing_City", "Billing_State", "Billing_Zip",
                    "Billing_Phone", "Billing_Email")
        missing = [field for field in required if not billing.get(field)]
        if not customer_name:
            missing.append("Billing_CustomerName")
        if missing:
            frappe.throw(_("Complete the dealer's ACH billing profile before initiating: {0}").format(
                ", ".join(missing)))
        if self.settings.default_sec_code == "WEB" and not customer_ip:
            frappe.throw(_("WEB payments require the captured customer authorization IP"))
        if token_source not in (None, "", "Manual", "ACHQ", "Plaid"):
            frappe.throw(_("Unsupported bank token source"))
        params = {key: value for key, value in billing.items() if key.startswith("Billing_")}
        params.update({
            "Amount": f"{float(amount):.2f}", "AccountToken": token,
            "PaymentDirection": "FromCustomer", "SECCode": self.settings.default_sec_code,
            "Billing_CustomerName": customer_name, "Billing_Company": customer_name,
            "Description": description[:50] if description else "",
            "Merchant_ReferenceID": txn_id, "Provider_TransactionID": txn_id,
            "TokenSource": "Plaid" if token_source == "Plaid" else "ACHQ",
            "SendEmailToCustomer": "No",
            "Run_ExpressVerify": "Yes" if self.settings.use_express_verify else "No",
        })
        if customer_ip:
            params["Customer_IPAddress"] = customer_ip
        return params

    def create_payment(self, amount, token, customer_name, description, txn_id,
                       customer_ip=None, token_source=None, billing=None):
        params = self.payment_parameters(amount, token, customer_name, description, txn_id,
            customer_ip=customer_ip, token_source=token_source, billing=billing)
        result = self._make_request("ECheck.ProcessPayment", params)
        reference = result.get("TransAct_ReferenceID") or result.get("Transact_ReferenceID")
        if result.get("success") and not reference:
            return {"success": False, "outcome_unknown": True,
                "error_message": "ACHQ accepted payment without a usable reference; reconcile by merchant reference"}
        if result.get("success"):
            return {"success": True, "transaction_id": reference,
                "status": result.get("PaymentStatus", "Scheduled"), "transact_reference_id": reference}
        return result

    def _parse_status_response(self, response_text):
        """Reports are CSV: direct merchant has 10 columns, platform mode 11."""
        if response_text.lstrip().startswith("{"):
            result = self._parse_response(response_text)
            if result.get("success"):
                result["transactions"] = result.get("Transactions") or []
            return result
        if not response_text.strip():
            return {"success": False, "error_message": "Empty status report; no successful acknowledgement"}
        rows = []
        unidentifiable_rows = 0
        try:
            for row in csv.reader(io.StringIO(response_text), strict=True):
                if not row or not any(row):
                    continue
                if len(row) not in (10, 11):
                    raise ValueError("Unexpected status report format")
                if not row[0]:
                    unidentifiable_rows += 1
                    continue
                if not row[0].isdigit():
                    raise ValueError("Unexpected provider reference in status report")
                platform = len(row) == 11
                if platform and row[2] != str(self.settings.achq_merchant_id):
                    continue
                offset = 1 if platform else 0
                if not row[4 + offset]:
                    raise ValueError("Status report row has no resulting status")
                rows.append({"TransAct_ReferenceID": row[0], "Merchant_ReferenceID": row[1],
                    "PaymentStatus": row[4 + offset], "ReturnCode": row[5 + offset] or None,
                    "ReturnDescription": row[6 + offset] or None,
                    "Event": row[2 + offset], "EventDate": row[3 + offset]})
        except (ValueError, csv.Error) as error:
            return {"success": False, "error_message": str(error)}
        if unidentifiable_rows:
            frappe.logger().warning(f"ACHQ status report: skipped {unidentifiable_rows} rows without a provider reference")
        return {"success": True, "transactions": rows, "unidentifiable_rows": unidentifiable_rows}

    def get_status_by_date(self, tracking_date):
        """
        Get all payment status updates for a given date.

        This is the correct way to poll for status updates in ACHQ.
        Returns all transactions that had status changes on the specified date.

        Args:
            tracking_date: Date to query (date object or string YYYY-MM-DD)

        Returns:
            dict with success, transactions list
        """
        if isinstance(tracking_date, str):
            tracking_date = getdate(tracking_date)

        # ACHQ expects MMDDYYYY format
        date_str = tracking_date.strftime("%m%d%Y")

        params = {
            "TrackingDate": date_str,
        }

        result = self._make_request("ECheckReports.StatusTrackingQuery", params, response_parser=self._parse_status_response)

        if result.get("success"):
            # Parse transactions from response
            transactions = result.get("transactions", result.get("Transactions", []))
            if not isinstance(transactions, list):
                transactions = [transactions] if transactions else []

            return {
                "success": True,
                "transactions": transactions,
                "tracking_date": tracking_date,
                "unidentifiable_rows": result.get("unidentifiable_rows", 0),
            }

        return result

    def cancel_payment(self, transaction_id):
        """
        Cancel a scheduled payment.

        Args:
            transaction_id: ACHQ transaction ID

        Returns:
            dict with success
        """
        params = {
            "Transact_ReferenceID": transaction_id,
        }

        result = self._make_request("ECheck.Void", params)
        return result


def get_customer_billing_details(customer):
    """Use the dealer's primary address/contact; never invent missing billing data."""
    from dcr.api.lending import _get_customer_address_details, _get_customer_contact_details
    address = _get_customer_address_details(customer)
    contact = _get_customer_contact_details(customer)
    return {"Billing_Address1": address.get("address_line_1"),
        "Billing_Address2": address.get("address_line_2"), "Billing_City": address.get("city"),
        "Billing_State": address.get("state"), "Billing_Zip": address.get("zip_code"),
        "Billing_Phone": contact.get("phone"), "Billing_Email": contact.get("email")}


def _verify_achq_webhook():
    """Verify ACHQ webhook request via HMAC signature + IP whitelist.

    Fail-closed: rejects all requests if no webhook secret is configured.
    """
    settings = frappe.get_single("ACH Settings")

    # IP whitelist check
    allowed_ips_csv = settings.get("achq_allowed_ips") or ""
    if allowed_ips_csv:
        allowed = {ip.strip() for ip in allowed_ips_csv.split(",") if ip.strip()}
        if allowed:
            client_ip = frappe.local.request_ip
            if client_ip not in allowed:
                frappe.logger().warning(f"ACHQ webhook: request from unauthorized IP {client_ip}")
                return False

    # HMAC signature check
    webhook_secret = settings.get_password("achq_webhook_secret") if settings.achq_webhook_secret else ""

    if not webhook_secret:
        frappe.logger().warning("ACHQ webhook: no webhook secret configured — rejecting request")
        return False

    signature = frappe.request.headers.get("X-ACHQ-Signature")
    if not signature:
        frappe.logger().warning("ACHQ webhook: missing signature header")
        return False

    body = frappe.request.get_data()
    expected = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        frappe.logger().warning("ACHQ webhook: signature mismatch")
        return False

    return True


@frappe.whitelist(allow_guest=True)
def achq_webhook():
    """
    Handle ACHQ webhook callbacks.

    URL: /api/method/dcr.api.achq_integration.achq_webhook

    Handles events:
    - Payment Cleared
    - Payment Returned
    - Payment Failed
    """
    try:
        # Verify the request comes from ACHQ
        if not _verify_achq_webhook():
            frappe.local.response["http_status_code"] = 403
            return {"status": "error", "message": "Unauthorized"}

        # Get webhook data
        data = frappe.local.form_dict

        # Log incoming webhook (redact sensitive fields)
        safe_data = {
            "TransactionID": data.get("TransactionID", "")[:8] + "..." if data.get("TransactionID") else "",
            "PaymentStatus": data.get("PaymentStatus"),
            "ReturnCode": data.get("ReturnCode"),
        }
        frappe.logger().info(f"ACHQ Webhook received: {safe_data}")

        if not apply_achq_status_update(data):
            frappe.local.response["http_status_code"] = 404
            return {"status": "error", "message": "Transaction not found"}

        frappe.db.commit()

        return {"status": "success"}

    except Exception as e:
        frappe.log_error(
            f"ACHQ Webhook error: {str(e)}",
            "ACHQ Webhook Error"
        )
        frappe.db.rollback()
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": "Internal error"}


def apply_achq_status_update(data):
    """Shared webhook/poll handler. Caller must authenticate the provider first."""
    merchant_ref = data.get("Merchant_ReferenceID")
    provider_ref = data.get("TransAct_ReferenceID") or data.get("Transact_ReferenceID")
    legacy_ref = data.get("TransactionID")
    name = merchant_ref if merchant_ref and frappe.db.exists("ACH Transaction", merchant_ref) else None
    if not name and (provider_ref or legacy_ref):
        name = frappe.db.get_value("ACH Transaction", {"achq_transaction_id": provider_ref or legacy_ref}, "name")
    if not name:
        return False
    frappe.db.get_value("ACH Transaction", name, "name", for_update=True)
    txn = frappe.get_doc("ACH Transaction", name)
    txn.flags.ignore_permissions = True
    if provider_ref and txn.achq_transaction_id and provider_ref != txn.achq_transaction_id:
        if txn.achq_reference_kind == "TransAct Reference" or legacy_ref != txn.achq_transaction_id:
            raise ValueError("Provider reference does not match this ACH transaction")
    if data.get("Amount") is not None and round(float(data["Amount"]), 2) != round(float(txn.amount), 2):
        raise ValueError("Provider amount does not match this ACH transaction")
    if provider_ref:
        txn.achq_transaction_id = provider_ref
        txn.achq_reference_kind = "TransAct Reference"
    status = str(data.get("PaymentStatus") or "")
    normalized = "".join(c for c in status.lower() if c.isalnum())
    txn.achq_status = status
    if normalized in ("cleared", "settled", "success"):
        txn.mark_success(achq_status=status)
    elif normalized in ("returned", "returnednsf", "returnedother", "chargedback"):
        txn.mark_failed(returned=True, return_code=data.get("ReturnCode"), failure_reason=data.get("ReturnDescription"))
    elif normalized in ("failed", "declined", "rejected") and txn.status not in ("Success", "Accounting Pending", "Returned", "Reversal Pending", "Cancelled"):
        txn.mark_failed(failure_code=data.get("ResponseCode"), failure_reason=data.get("Description") or "Payment rejected")
    elif normalized == "cancelled" and txn.status not in ("Success", "Accounting Pending", "Returned", "Reversal Pending"):
        txn.status = "Cancelled"
        txn.next_retry_date = None
    elif normalized in ("inprocess", "processing") and txn.status in ("Initiated", "Outcome Unknown", "Scheduled"):
        txn.status = "Processing"
    elif normalized == "scheduled" and txn.status == "Outcome Unknown":
        txn.status = "Initiated"
    txn.save()
    return True


def _check_rate_limit(key, limit, window_hours=24):
    """Check rate limit using Frappe cache.

    Args:
        key: Unique key for the rate limit (e.g. "bank_account:CUST-001")
        limit: Max allowed actions in the window
        window_hours: Time window in hours

    Raises:
        frappe.ValidationError if limit exceeded
    """
    cache_key = f"rate_limit:{key}"
    count = frappe.cache.get_value(cache_key) or 0
    if count >= limit:
        frappe.throw(_("Rate limit exceeded. Please try again later."))
    frappe.cache.set_value(cache_key, count + 1, expires_in_sec=window_hours * 3600)


def _validate_routing_number(routing_number):
    """Validate ABA routing number format and checksum.

    The ABA checksum algorithm:
    3(d1 + d4 + d7) + 7(d2 + d5 + d8) + (d3 + d6 + d9) mod 10 == 0
    """
    if not routing_number.isdigit() or len(routing_number) != 9:
        frappe.throw(_("Routing number must be exactly 9 digits"))

    digits = [int(d) for d in routing_number]
    checksum = (
        3 * (digits[0] + digits[3] + digits[6])
        + 7 * (digits[1] + digits[4] + digits[7])
        + (digits[2] + digits[5] + digits[8])
    )
    if checksum % 10 != 0:
        frappe.throw(_("Invalid routing number"))


def _validate_account_number(account_number):
    """Validate bank account number format."""
    if not account_number.isdigit():
        frappe.throw(_("Account number must contain only digits"))
    if len(account_number) < 4 or len(account_number) > 17:
        frappe.throw(_("Account number must be between 4 and 17 digits"))


def _send_connected_email(customer, bank_name, account_last4):
    """Send confirmation email to dealer that bank account is connected."""
    # The existing external template promises automatic debits. Until that
    # template supports a bank-only confirmation, do not send it with ACH off.
    from dcr.dcr.doctype.ach_settings.ach_settings import is_ach_enabled
    if not is_ach_enabled():
        return
    try:
        customer_email = frappe.db.get_value("Customer", customer, "email_id")
        if not customer_email:
            return
        customer_name = frappe.db.get_value("Customer", customer, "customer_name")

        from dcr.api.dcr_email import send_autopay_connected
        send_autopay_connected(
            customer_name=customer_name or customer,
            bank_name=bank_name,
            account_last4=account_last4,
            to_email=customer_email,
            reference_name=customer,
        )
    except Exception:
        frappe.log_error("Failed to send autopay connected email", "ACH Setup")


def _get_or_create_bank(bank_name):
    """Find or create a Bank doctype record for the given bank name."""
    if not bank_name:
        return None
    existing = frappe.db.get_value("Bank", {"bank_name": bank_name}, "name")
    if existing:
        return existing
    bank = frappe.new_doc("Bank")
    bank.bank_name = bank_name
    bank.insert(ignore_permissions=True)
    return bank.name


def _create_bank_account(customer, bank_name, account_type, token, token_source,
                         verify_status, account_last4, routing_last4, is_default, settings):
    """Create a Bank Account record with ACH custom fields."""
    bank_record = _get_or_create_bank(bank_name)

    ba = frappe.new_doc("Bank Account")
    ba.account_name = f"{customer} - {bank_name or 'Bank'} {account_last4}"
    ba.bank = bank_record
    ba.party_type = "Customer"
    ba.party = customer
    ba.is_default = 1 if is_default else 0
    ba.is_company_account = 0
    ba.account_type = account_type

    # ACH custom fields
    ba.custom_ach_status = "Active"
    ba.custom_achq_token = token
    ba.custom_token_source = token_source
    ba.custom_account_last_four = account_last4
    ba.custom_routing_last_4 = routing_last4
    ba.custom_verification_status = verify_status
    ba.custom_consent_captured = 1
    ba.custom_authorization_ip = frappe.local.request_ip if hasattr(frappe.local, 'request_ip') else ""
    ba.custom_authorization_date = now_datetime()
    ba.custom_sec_code = settings.default_sec_code

    ba.insert()
    return ba


@frappe.whitelist()
def setup_bank_account(customer, routing_number, account_number, account_type, is_default=True, check_type=None):
    """
    Set up a bank account for ACH autopay using manual entry.

    Creates a Bank Account linked to the customer.

    Args:
        customer: Customer name
        routing_number: 9-digit routing number
        account_number: Bank account number
        account_type: 'Checking' or 'Savings'
        is_default: Set as default payment account (default True)
        check_type: 'Personal' or 'Business' (optional)

    Returns:
        dict with success, bank_name, account_last4, bank_account_name
    """
    require_staff("Customer", customer, "write")
    if not customer or not routing_number or not account_number:
        frappe.throw(_("Customer, routing number, and account number are required"))

    routing_number = routing_number.strip()
    account_number = account_number.strip()

    _validate_routing_number(routing_number)
    _validate_account_number(account_number)

    if account_type not in ("Checking", "Savings"):
        frappe.throw(_("Account type must be Checking or Savings"))

    _check_rate_limit(f"bank_account:{customer}", limit=5)

    customer_name = frappe.db.get_value("Customer", customer, "customer_name")
    if not customer_name:
        frappe.throw(_("Customer not found"))

    client = ACHQClient()
    result = client.tokenize_and_verify(
        routing_number=routing_number,
        account_number=account_number,
        account_type=account_type,
        customer_name=customer_name,
        check_type=check_type
    )

    if not result.get("success"):
        frappe.throw(_("Bank account verification failed: {0}").format(
            result.get("error_message", "Unknown error")
        ))

    verify_status = result.get("verify_status", "UNK")

    if verify_status == "NEG":
        frappe.throw(_("Bank account verification failed. This account cannot be used for autopay."))

    settings = frappe.get_single("ACH Settings")
    if verify_status == "UNK" and not settings.allow_unknown_accounts:
        frappe.throw(_("Bank account could not be verified. Please contact support."))

    is_default = is_default in [True, 1, "1", "true", "True"]

    ba = _create_bank_account(
        customer=customer,
        bank_name=result.get("bank_name", ""),
        account_type=account_type,
        token=result.get("token"),
        token_source="Manual",
        verify_status=verify_status,
        account_last4=result.get("account_last4", ""),
        routing_last4=result.get("routing_last4", ""),
        is_default=is_default,
        settings=settings,
    )

    frappe.db.commit()

    _send_connected_email(customer, result.get("bank_name", ""), result.get("account_last4", ""))

    return {
        "success": True,
        "bank_name": result.get("bank_name", ""),
        "account_last4": result.get("account_last4", ""),
        "bank_account_name": ba.name,
        "verification_status": verify_status,
        "is_default": ba.is_default,
        "message": "Bank account successfully linked for autopay"
    }


@frappe.whitelist()
def pause_bank_account(bank_account_name, reason=None):
    """Pause ACH on a bank account."""
    require_staff("Bank Account", bank_account_name, "write")
    from dcr.api.bank_account_ach import pause
    pause(bank_account_name, reason)
    return {"success": True, "message": "Bank account paused"}


@frappe.whitelist()
def resume_bank_account(bank_account_name):
    """Resume ACH on a paused bank account."""
    require_staff("Bank Account", bank_account_name, "write")
    from dcr.api.bank_account_ach import resume
    resume(bank_account_name)
    return {"success": True, "message": "Bank account resumed"}


@frappe.whitelist()
def revoke_bank_account(bank_account_name, reason=None):
    """Revoke ACH on a bank account."""
    require_staff("Bank Account", bank_account_name, "write")
    from dcr.api.bank_account_ach import revoke
    result = revoke(bank_account_name, reason)
    return {"success": True, "message": "Bank account revoked",
            "unresolved_transactions": result.get("unresolved_transactions", [])}


# =============================================================================
# Multi-Account Management APIs
# =============================================================================

@frappe.whitelist()
def get_customer_accounts(customer):
    """
    Get all ACH-enabled bank accounts for a customer.

    Args:
        customer: Customer name

    Returns:
        dict with accounts list
    """
    require_staff("Customer", customer)
    require_staff("Bank Account")
    accounts = frappe.get_list(
        "Bank Account",
        filters={
            "party_type": "Customer",
            "party": customer,
            "custom_ach_status": ["in", ["Active", "Paused"]]
        },
        fields=[
            "name", "custom_ach_status as status", "bank", "custom_account_last_four as bank_account_last4",
            "is_default", "custom_token_source as token_source", "custom_authorization_date as authorization_date"
        ],
        order_by="is_default desc, custom_authorization_date desc"
    )

    # Resolve bank names
    for acc in accounts:
        acc["bank_name"] = frappe.db.get_value("Bank", acc.get("bank"), "bank_name") if acc.get("bank") else ""

    return {
        "success": True,
        "accounts": accounts,
        "count": len(accounts)
    }


@frappe.whitelist()
def set_default_account(bank_account_name):
    """
    Set a bank account as the default for the customer.

    Args:
        bank_account_name: Bank Account name

    Returns:
        dict with success
    """
    require_staff("Bank Account", bank_account_name, "write")
    from dcr.api.bank_account_ach import set_as_default
    set_as_default(bank_account_name)
    return {"success": True, "message": "Account set as default"}


@frappe.whitelist()
def set_loan_account(loan, bank_account_name):
    """
    Set a specific bank account for a loan (override default).

    Args:
        loan: Loan name
        bank_account_name: Bank Account name (or empty to clear override)

    Returns:
        dict with success
    """
    require_staff("Loan", loan, "write")
    loan_doc = frappe.get_doc("Loan", loan)

    if bank_account_name:
        ba = frappe.get_doc("Bank Account", bank_account_name)
        ba.check_permission("read")
        if ba.party_type != loan_doc.applicant_type or ba.party != loan_doc.applicant:
            frappe.throw(_("This bank account does not belong to this customer"))
        if ba.get("custom_ach_status") != "Active":
            frappe.throw(_("This bank account is not active"))

        loan_doc.ach_payment_account = bank_account_name
    else:
        loan_doc.ach_payment_account = None

    loan_doc.save()
    frappe.db.commit()

    return {"success": True, "message": "Loan payment account updated"}


@frappe.whitelist()
def get_loan_account_info(loan):
    """
    Get the effective payment account info for a loan with resolution details.

    Args:
        loan: Loan name

    Returns:
        dict with account info and resolution source
    """
    require_staff("Loan", loan)
    from dcr.api.bank_account_ach import get_loan_payment_account

    loan_doc = frappe.get_doc("Loan", loan)
    ba = get_loan_payment_account(loan_doc)

    if not ba:
        return {
            "has_account": False,
            "resolution": "none",
            "message": "No payment account configured"
        }

    if loan_doc.get("ach_payment_account"):
        resolution = "loan_override"
    else:
        resolution = "customer_default"

    bank_name = frappe.db.get_value("Bank", ba.bank, "bank_name") if ba.bank else ""

    return {
        "has_account": True,
        "bank_account_name": ba.name,
        "bank_name": bank_name,
        "account_last4": ba.custom_account_last_four,
        "status": ba.get("custom_ach_status"),
        "is_default": ba.is_default,
        "token_source": ba.custom_token_source,
        "resolution": resolution
    }


# =============================================================================
# Plaid Integration APIs
# =============================================================================

@frappe.whitelist()
def get_plaid_link_token(customer):
    """
    Get a Plaid Link token for the frontend.

    This initiates the Plaid Link flow. The token is used by the frontend
    to open Plaid Link UI.

    Args:
        customer: Customer name

    Returns:
        dict with link_token
    """
    require_staff("Customer", customer, "write")
    settings = frappe.get_single("ACH Settings")

    if not settings.has_plaid_credentials():
        frappe.throw(_("Plaid is not configured"))

    # Rate limit: max 10 link token requests per customer per day
    _check_rate_limit(f"plaid_link:{customer}", limit=10)

    # Get Plaid API credentials
    plaid_client_id = settings.plaid_client_id
    plaid_secret = settings.get_password("plaid_secret")
    plaid_base_url = settings.get_plaid_base_url()

    # Get customer info for Plaid
    customer_doc = frappe.get_doc("Customer", customer)

    try:
        response = requests.post(
            f"{plaid_base_url}/link/token/create",
            json={
                "client_id": plaid_client_id,
                "secret": plaid_secret,
                "user": {
                    "client_user_id": customer
                },
                "client_name": frappe.defaults.get_global_default("company") or "Dealer Capital Resources",
                "products": ["auth"],
                "country_codes": ["US"],
                "language": "en",
                "account_filters": {
                    "depository": {
                        "account_subtypes": ["checking", "savings"]
                    }
                }
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        return {
            "success": True,
            "link_token": result.get("link_token"),
            "expiration": result.get("expiration")
        }

    except requests.RequestException as e:
        frappe.log_error(f"Plaid link token request failed: {str(e)}", "Plaid Integration")
        frappe.throw(_("Failed to initialize bank connection. Please try again."))


@frappe.whitelist()
def process_plaid_callback(public_token, account_id, customer, is_default=True):
    """
    Process the Plaid Link callback.

    After user completes Plaid Link:
    1. Exchange public_token for access_token
    2. Create processor_token for ACHQ
    3. Get account details
    4. Create Bank Account

    Args:
        public_token: Plaid public_token from Link callback
        account_id: Selected account ID from Plaid
        customer: Customer name
        is_default: Set as default payment account (default True)

    Returns:
        dict with success, authorization_name, bank_name, account_last4
    """
    require_staff("Customer", customer, "write")
    settings = frappe.get_single("ACH Settings")

    if not settings.has_plaid_credentials():
        frappe.throw(_("Plaid is not configured"))

    # Rate limit: max 5 Plaid callbacks per customer per day
    _check_rate_limit(f"plaid_callback:{customer}", limit=5)

    plaid_client_id = settings.plaid_client_id
    plaid_secret = settings.get_password("plaid_secret")
    plaid_base_url = settings.get_plaid_base_url()

    try:
        # Step 1: Exchange public_token for access_token
        exchange_response = requests.post(
            f"{plaid_base_url}/item/public_token/exchange",
            json={
                "client_id": plaid_client_id,
                "secret": plaid_secret,
                "public_token": public_token
            },
            timeout=30
        )
        exchange_response.raise_for_status()
        exchange_result = exchange_response.json()
        access_token = exchange_result.get("access_token")

        # Step 2: Read Auth for the selected account, including its routing
        # identifier. Retain only the mask in DCR; ACHQ uses the processor token.
        accounts_response = requests.post(
            f"{plaid_base_url}/auth/get",
            json={
                "client_id": plaid_client_id,
                "secret": plaid_secret,
                "access_token": access_token,
                "options": {"account_ids": [account_id]},
            },
            timeout=30
        )
        accounts_response.raise_for_status()
        accounts_result = accounts_response.json()

        # Find the selected account
        account_info = None
        for acc in accounts_result.get("accounts", []):
            if acc.get("account_id") == account_id:
                account_info = acc
                break

        if not account_info:
            frappe.throw(_("Selected account not found"))

        ach_numbers = next((row for row in (accounts_result.get("numbers") or {}).get("ach") or []
                            if row.get("account_id") == account_id), None)
        routing = str((ach_numbers or {}).get("routing") or "")
        if len(routing) != 9 or not routing.isascii() or not routing.isdigit():
            frappe.throw(_("Plaid did not return ACH routing details for the selected account. Please connect a verified US checking or savings account."))
        routing_last4 = routing[-4:]

        # Step 3: Create processor token for ACHQ
        processor_response = requests.post(
            f"{plaid_base_url}/processor/token/create",
            json={
                "client_id": plaid_client_id,
                "secret": plaid_secret,
                "access_token": access_token,
                "account_id": account_id,
                "processor": "achq"
            },
            timeout=30
        )
        processor_response.raise_for_status()
        processor_result = processor_response.json()
        processor_token = processor_result.get("processor_token")

        # Get institution info
        institution = accounts_result.get("item", {}).get("institution_id", "")
        bank_name = ""
        if institution:
            try:
                inst_response = requests.post(
                    f"{plaid_base_url}/institutions/get_by_id",
                    json={
                        "client_id": plaid_client_id,
                        "secret": plaid_secret,
                        "institution_id": institution,
                        "country_codes": ["US"]
                    },
                    timeout=30
                )
                inst_response.raise_for_status()
                bank_name = inst_response.json().get("institution", {}).get("name", "")
            except (requests.RequestException, KeyError, ValueError):
                pass  # Bank name is optional

        is_default = is_default in [True, 1, "1", "true", "True"]

        resolved_bank_name = bank_name or account_info.get("name", "")
        account_last4 = account_info.get("mask", "")[-4:] if account_info.get("mask") else ""

        # Step 4: Create Bank Account
        ba = _create_bank_account(
            customer=customer,
            bank_name=resolved_bank_name,
            account_type="Checking" if account_info.get("subtype") == "checking" else "Savings",
            token=processor_token,
            token_source="Plaid",
            verify_status="POS",  # Plaid-verified accounts are considered positive
            account_last4=account_last4,
            routing_last4=routing_last4,
            is_default=is_default,
            settings=settings,
        )

        frappe.db.commit()

        _send_connected_email(customer, resolved_bank_name, account_last4)

        return {
            "success": True,
            "bank_account_name": ba.name,
            "bank_name": resolved_bank_name,
            "account_last4": account_last4,
            "is_default": ba.is_default,
            "message": "Bank account successfully connected via Plaid"
        }

    except requests.RequestException as e:
        frappe.log_error(f"Plaid callback processing failed: {str(e)}", "Plaid Integration")
        frappe.throw(_("Failed to connect bank account. Please try again."))


@frappe.whitelist()
def is_plaid_available():
    """
    Check if Plaid integration is available and configured.

    Returns:
        dict with available boolean and environment
    """
    from dcr.dcr.doctype.ach_settings.ach_settings import is_plaid_enabled

    settings = frappe.get_single("ACH Settings")

    return {
        "available": is_plaid_enabled(),
        "environment": settings.plaid_environment if settings.has_plaid_credentials() else None
    }


# ---------------------------------------------------------------------------
# Guest-accessible Plaid endpoints (token-verified, for /plaid-setup page)
# ---------------------------------------------------------------------------

def _verify_plaid_guest_token(customer, token):
    """Verify the HMAC token from a Plaid setup URL."""
    from dcr.www.plaid_setup import verify_plaid_token
    if not customer or not token:
        frappe.throw(_("Invalid request"), frappe.AuthenticationError)
    if not verify_plaid_token(customer, token):
        frappe.throw(_("Invalid or expired link"), frappe.AuthenticationError)


@frappe.whitelist(allow_guest=True)
def get_plaid_link_token_guest(customer, token):
    """Guest-accessible wrapper for get_plaid_link_token. Verified via HMAC token."""
    with _plaid_token_context(customer, token):
        return get_plaid_link_token(customer)


@frappe.whitelist(allow_guest=True)
def process_plaid_callback_guest(public_token, account_id, customer, token):
    """Guest-accessible wrapper for process_plaid_callback. Verified via HMAC token."""
    with _plaid_token_context(customer, token):
        return process_plaid_callback(public_token, account_id, customer, is_default=True)


@contextmanager
def _plaid_token_context(customer, token):
    """Keep token-authorized work from replacing the caller's session cookie.

    Frappe set_user resets sid, session data and request arguments, so restoring
    just the username still leaves a signed-in browser with an invalid sid.
    """
    _verify_plaid_guest_token(customer, token)
    original_session = dict(frappe.local.session)
    original_form = frappe.local.form_dict
    try:
        frappe.set_user("Administrator")
        yield
    finally:
        frappe.set_user(original_session['user'])
        frappe.local.session.update(original_session)
        frappe.local.form_dict = original_form
