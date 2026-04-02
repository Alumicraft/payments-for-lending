# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
ACHQ Integration Module

Provides client for ACHQ API operations and webhook handling.
Based on ACHQ API documentation at developers.achq.com
"""

import hashlib
import hmac
import json

import frappe
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

    def __init__(self):
        self.settings = frappe.get_single("ACH Settings")
        self._validate_settings()

    def _validate_settings(self):
        """Validate that required settings are configured."""
        if not self.settings.enable_ach_autopay:
            frappe.throw(_("ACH Autopay is not enabled"))

    def _get_auth_params(self):
        """Get authentication parameters for Direct Merchant mode."""
        params = {
            "MerchantID": self.settings.achq_merchant_id,
            "Merchant_GateID": self.settings.achq_merchant_gate_id,
            "Merchant_GateKey": self.settings.get_password("achq_merchant_gate_key"),
        }

        # Add TestMode for sandbox
        if self.settings.achq_environment == "Sandbox":
            params["TestMode"] = "On"

        return params

    def _make_request(self, command, params):
        """Make a request to ACHQ API."""
        data = self._get_auth_params()
        data["Command"] = command
        data["CommandVersion"] = "2.0"
        data["ResponseType"] = "JSON"
        data.update(params)

        try:
            response = requests.post(self.BASE_URL, data=data, timeout=30)
            response.raise_for_status()
            return self._parse_response(response.text)
        except requests.RequestException as e:
            frappe.log_error(
                f"ACHQ API request failed: {str(e)}",
                "ACHQ Integration"
            )
            return {"success": False, "error_message": str(e)}

    # Expected top-level keys in valid ACHQ responses
    _VALID_RESPONSE_KEYS = {
        "CommandStatus", "ResponseCode", "Description", "ErrorInformation",
        "TransactionID", "TransAct_ReferenceID", "ACHQToken", "BankName",
        "ExpressVerify", "PaymentStatus", "Transactions",
    }

    def _parse_response(self, response_text):
        """Parse and validate ACHQ JSON response."""
        if not response_text:
            return {"success": False, "error_message": "Empty response"}

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            frappe.log_error(
                f"ACHQ response JSON parse error: {str(e)}\nResponse: {response_text[:500]}",
                "ACHQ Integration"
            )
            return {"success": False, "error_message": f"Invalid JSON response: {str(e)}"}

        # Basic schema validation — must be a dict with expected keys
        if not isinstance(result, dict):
            frappe.log_error(
                f"ACHQ response is not a JSON object: {type(result).__name__}",
                "ACHQ Integration"
            )
            return {"success": False, "error_message": "Invalid response format"}

        # Warn if response contains unexpected keys (possible tampering)
        unexpected = set(result.keys()) - self._VALID_RESPONSE_KEYS
        if unexpected:
            frappe.logger().warning(
                f"ACHQ response contains unexpected keys: {unexpected}"
            )

        # Check for success based on CommandStatus
        command_status = str(result.get("CommandStatus", "")).lower()
        response_code = str(result.get("ResponseCode", ""))

        if command_status == "approved" or response_code == "000":
            result["success"] = True
        else:
            result["success"] = False
            result["error_message"] = result.get("Description",
                result.get("ErrorInformation", {}).get("Message", "Unknown error")
                if isinstance(result.get("ErrorInformation"), dict)
                else result.get("ErrorInformation", "Unknown error")
            )
            result["error_code"] = response_code

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

    def create_payment(self, amount, token, customer_name, description, txn_id, customer_ip=None, token_source=None):
        """
        Create a payment using a tokenized account.

        Args:
            amount: Payment amount
            token: ACHQ token or Plaid processor_token
            customer_name: Customer's name
            description: Payment description
            txn_id: Internal transaction ID for tracking
            customer_ip: Customer's IP address (optional)
            token_source: 'Manual' or 'Plaid' - determines how token is processed

        Returns:
            dict with success, transaction_id, status
        """
        params = {
            "Amount": f"{float(amount):.2f}",
            "AccountToken": token,
            "PaymentDirection": "FromCustomer",
            "SECCode": self.settings.default_sec_code,
            "Billing_CustomerName": customer_name,
            "Description": description[:50] if description else "",
            "Merchant_ReferenceID": txn_id,
        }

        # For Plaid tokens, tell ACHQ the token source
        if token_source == "Plaid":
            params["TokenSource"] = "Plaid"

        if customer_ip:
            params["Customer_IPAddress"] = customer_ip

        result = self._make_request("ECheck.ProcessPayment", params)

        if result.get("success"):
            return {
                "success": True,
                "transaction_id": result.get("TransactionID"),
                "status": result.get("PaymentStatus", "Scheduled"),
                "transact_reference_id": result.get("TransAct_ReferenceID"),
            }

        return result

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

        result = self._make_request("ECheckReports.StatusTrackingQuery", params)

        if result.get("success"):
            # Parse transactions from response
            transactions = result.get("Transactions", [])
            if not isinstance(transactions, list):
                transactions = [transactions] if transactions else []

            return {
                "success": True,
                "transactions": transactions,
                "tracking_date": tracking_date,
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
            "TransactionID": transaction_id,
        }

        result = self._make_request("ECheck.CancelPayment", params)
        return result


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

        # Extract key fields
        transaction_id = data.get("TransactionID")
        merchant_ref_id = data.get("Merchant_ReferenceID")
        payment_status = data.get("PaymentStatus", "").lower()
        return_code = data.get("ReturnCode")
        return_description = data.get("ReturnDescription")

        if not transaction_id and not merchant_ref_id:
            frappe.log_error("ACHQ Webhook: No transaction ID provided", "ACHQ Webhook")
            return {"status": "error", "message": "No transaction ID"}

        # Find the ACH Transaction
        txn = None
        if merchant_ref_id:
            # Merchant_ReferenceID is our internal transaction name
            if frappe.db.exists("ACH Transaction", merchant_ref_id):
                txn = frappe.get_doc("ACH Transaction", merchant_ref_id)

        if not txn and transaction_id:
            # Look up by ACHQ transaction ID
            txn_name = frappe.db.get_value(
                "ACH Transaction",
                {"achq_transaction_id": transaction_id},
                "name"
            )
            if txn_name:
                txn = frappe.get_doc("ACH Transaction", txn_name)

        if not txn:
            frappe.log_error(
                f"ACHQ Webhook: Transaction not found - ACHQ ID: {transaction_id}, Merchant Ref: {merchant_ref_id}",
                "ACHQ Webhook"
            )
            return {"status": "error", "message": "Transaction not found"}

        # Update transaction based on status
        txn.achq_status = payment_status

        if payment_status in ("cleared", "settled", "success"):
            txn.mark_success(achq_status=payment_status)
        elif payment_status in ("returned", "returned-nsf", "returned-other", "chargedback"):
            txn.mark_failed(
                failure_code=return_code,
                failure_reason=return_description,
                return_code=return_code
            )
        elif payment_status in ("failed", "declined", "rejected"):
            txn.mark_failed(
                failure_code=return_code or "FAILED",
                failure_reason=return_description or "Payment failed"
            )
        elif payment_status == "cancelled":
            if txn.status not in ("Cancelled", "Success"):
                txn.status = "Cancelled"
                txn.save()

        frappe.db.commit()

        return {"status": "success"}

    except Exception as e:
        frappe.log_error(
            f"ACHQ Webhook error: {str(e)}",
            "ACHQ Webhook Error"
        )
        return {"status": "error", "message": "Internal error"}


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

    # ACH custom fields
    ba.ach_status = "Active"
    ba.achq_token = token
    ba.token_source = token_source
    ba.bank_account_last4 = account_last4
    ba.routing_number_last4 = routing_last4
    ba.verification_status = verify_status
    ba.consent_captured = 1
    ba.authorization_ip = frappe.local.request_ip if hasattr(frappe.local, 'request_ip') else ""
    ba.authorization_date = now_datetime()
    ba.sec_code = settings.default_sec_code

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
    from dcr.api.bank_account_ach import pause
    pause(bank_account_name, reason)
    return {"success": True, "message": "Bank account paused"}


@frappe.whitelist()
def resume_bank_account(bank_account_name):
    """Resume ACH on a paused bank account."""
    from dcr.api.bank_account_ach import resume
    resume(bank_account_name)
    return {"success": True, "message": "Bank account resumed"}


@frappe.whitelist()
def revoke_bank_account(bank_account_name, reason=None):
    """Revoke ACH on a bank account."""
    from dcr.api.bank_account_ach import revoke
    revoke(bank_account_name, reason)
    return {"success": True, "message": "Bank account revoked"}


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
    accounts = frappe.get_all(
        "Bank Account",
        filters={
            "party_type": "Customer",
            "party": customer,
            "ach_status": ["in", ["Active", "Paused"]]
        },
        fields=[
            "name", "ach_status as status", "bank", "bank_account_last4",
            "is_default", "token_source", "authorization_date"
        ],
        order_by="is_default desc, authorization_date desc"
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
    loan_doc = frappe.get_doc("Loan", loan)

    if bank_account_name:
        ba = frappe.get_doc("Bank Account", bank_account_name)
        if ba.party != loan_doc.applicant:
            frappe.throw(_("This bank account does not belong to this customer"))
        if ba.get("ach_status") != "Active":
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
        "account_last4": ba.bank_account_last4,
        "status": ba.get("ach_status"),
        "is_default": ba.is_default,
        "token_source": ba.token_source,
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

        # Step 2: Get account details
        accounts_response = requests.post(
            f"{plaid_base_url}/accounts/get",
            json={
                "client_id": plaid_client_id,
                "secret": plaid_secret,
                "access_token": access_token
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
            routing_last4="",  # Not available from Plaid directly
            is_default=is_default,
            settings=settings,
        )

        frappe.db.commit()

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
