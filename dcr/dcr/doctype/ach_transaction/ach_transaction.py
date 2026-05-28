# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, add_days, getdate, today

# Return codes that CAN be retried (typically funding issues)
RETRYABLE_RETURN_CODES = {
    "R01": "Insufficient Funds",
    "R09": "Uncollected Funds",
}

# Return codes that should NOT be retried (account/authorization issues)
NON_RETRYABLE_RETURN_CODES = {
    "R02": "Account Closed",
    "R03": "No Account/Unable to Locate",
    "R04": "Invalid Account Number",
    "R05": "Unauthorized Debit to Consumer Account",
    "R07": "Authorization Revoked by Customer",
    "R08": "Payment Stopped",
    "R10": "Customer Advises Unauthorized",
    "R11": "Check Truncation Entry Return",
    "R16": "Account Frozen",
    "R20": "Non-Transaction Account",
    "R29": "Corporate Customer Advises Not Authorized",
}

# ACHQ internal rejection codes (pre-flight failures)
ACHQ_REJECTION_CODES = {
    "D01": "Duplicate Transaction",
    "S01": "Invalid Routing Number",
    "S02": "Known Bad Account",
    "S10": "Invalid Account Type",
    "S11": "Invalid Check Type",
    "S12": "Invalid Amount",
    "S13": "Invalid Merchant Reference ID",
}


class ACHTransaction(Document):
    def validate(self):
        self._set_customer_from_account()
        self._set_max_retries_from_settings()

    def _get_payment_account(self):
        """Get the Bank Account or legacy ACH Authorization for this transaction.

        Returns (doc, source) where source is 'bank_account' or 'ach_authorization'.
        """
        if self.bank_account:
            return frappe.get_doc("Bank Account", self.bank_account), "bank_account"
        if self.ach_authorization:
            return frappe.get_doc("ACH Authorization", self.ach_authorization), "ach_authorization"
        return None, None

    def _set_customer_from_account(self):
        """Fetch customer from the payment account if not set."""
        if self.customer:
            return
        if self.bank_account:
            self.customer = frappe.db.get_value("Bank Account", self.bank_account, "party")
        elif self.ach_authorization:
            self.customer = frappe.db.get_value(
                "ACH Authorization", self.ach_authorization, "customer"
            )

    def _set_max_retries_from_settings(self):
        """Set max retries from ACH Settings if this is a new transaction."""
        if self.is_new() and not self.max_retries:
            from dcr.dcr.doctype.ach_settings.ach_settings import get_ach_settings
            settings = get_ach_settings()
            self.max_retries = settings.max_retry_attempts

    def _get_token_and_source(self):
        """Get the ACHQ token and token_source from the payment account.

        Uses frappe.db.get_value for Bank Account since achq_token is a Data field.
        Uses get_password for legacy ACH Authorization since it's a Password field.
        """
        if self.bank_account:
            data = frappe.db.get_value(
                "Bank Account", self.bank_account,
                ["custom_achq_token", "custom_token_source"], as_dict=True
            )
            return data.custom_achq_token if data else None, data.custom_token_source if data else None
        if self.ach_authorization:
            auth = frappe.get_doc("ACH Authorization", self.ach_authorization)
            return auth.get_password("achq_token"), auth.token_source
        return None, None

    def _get_account_status(self):
        """Get the ACH status from the payment account."""
        if self.bank_account:
            return frappe.db.get_value("Bank Account", self.bank_account, "custom_ach_status")
        if self.ach_authorization:
            return frappe.db.get_value("ACH Authorization", self.ach_authorization, "status")
        return None

    def initiate(self):
        """Initiate the ACH transaction via ACHQ API."""
        if self.status != "Scheduled":
            frappe.throw(_("Only scheduled transactions can be initiated"))

        status = self._get_account_status()
        if status != "Active":
            frappe.throw(_("Payment account is not active"))

        token, token_source = self._get_token_and_source()
        if not token:
            frappe.throw(_("No payment token found on the payment account"))

        from dcr.api.achq_integration import ACHQClient

        customer_name = frappe.db.get_value("Customer", self.customer, "customer_name")

        client = ACHQClient()
        result = client.create_payment(
            amount=self.amount,
            token=token,
            customer_name=customer_name,
            description=f"Loan payment for {self.loan}",
            txn_id=self.name,
            token_source=token_source
        )

        if result.get("success"):
            self.status = "Initiated"
            self.achq_transaction_id = result.get("transaction_id")
            self.achq_status = result.get("status")
            self.initiated_date = now_datetime()
            self.settlement_date = add_days(today(), 5)
            self.save()
            return True
        else:
            self.status = "Failed"
            self.failure_code = result.get("error_code")
            self.failure_reason = result.get("error_message")
            self.save()
            return False

    def mark_success(self, achq_status=None):
        """Mark transaction as successful and create Payment Entry."""
        self.status = "Success"
        self.completed_date = now_datetime()
        if achq_status:
            self.achq_status = achq_status

        payment_entry = self.create_payment_entry()
        if payment_entry:
            self.payment_entry = payment_entry.name

        self.save()

        if not self.notification_sent:
            self.send_notification("success")

        return True

    def mark_failed(self, failure_code=None, failure_reason=None, return_code=None):
        """Mark transaction as failed and schedule retry if applicable."""
        if return_code:
            self.status = "Returned"
            self.return_code = return_code
        else:
            self.status = "Failed"

        self.failure_code = failure_code
        self.failure_reason = failure_reason
        self.completed_date = now_datetime()
        self.save()

        if self.should_retry(return_code):
            self.schedule_retry()

        if not self.notification_sent:
            self.send_notification("failure")

        return True

    def cancel_transaction(self, reason=None):
        """Cancel the transaction if still scheduled or initiated."""
        if self.status not in ("Scheduled", "Initiated"):
            frappe.throw(_("Only scheduled or initiated transactions can be cancelled"))

        if self.status == "Initiated" and self.achq_transaction_id:
            from dcr.api.achq_integration import ACHQClient
            client = ACHQClient()
            result = client.cancel_payment(self.achq_transaction_id)
            if not result.get("success"):
                frappe.log_error(
                    f"Failed to cancel ACHQ transaction {self.achq_transaction_id}: "
                    f"{result.get('error_message')}",
                    "ACH Transaction Cancellation"
                )

        self.status = "Cancelled"
        self.failure_reason = reason or "Cancelled by user"
        self.save()

        self.add_comment("Comment", f"Transaction cancelled: {reason or 'No reason provided'}")
        return True

    def should_retry(self, return_code):
        """Determine if the transaction should be retried based on return code."""
        if self.retry_attempt >= self.max_retries:
            return False

        if return_code and return_code in NON_RETRYABLE_RETURN_CODES:
            return False

        if return_code and return_code in ACHQ_REJECTION_CODES:
            return False

        # Any other code (including those in RETRYABLE_RETURN_CODES) is
        # retried until max_retries is hit.
        return True

    def schedule_retry(self):
        """Schedule a retry transaction."""
        from dcr.dcr.doctype.ach_settings.ach_settings import get_ach_settings
        settings = get_ach_settings()

        self.next_retry_date = add_days(today(), settings.retry_delay_days)
        self.save()

        self.add_comment(
            "Comment",
            f"Retry scheduled for {self.next_retry_date} (attempt {self.retry_attempt + 1} of {self.max_retries})"
        )

    def create_retry_transaction(self):
        """Create a new retry transaction."""
        if self.retry_attempt >= self.max_retries:
            frappe.throw(_("Maximum retry attempts reached"))

        # Verify payment account is still active
        status = self._get_account_status()
        if status != "Active":
            frappe.throw(_("Payment account is no longer active"))

        retry_txn = frappe.new_doc("ACH Transaction")
        retry_txn.bank_account = self.bank_account
        retry_txn.ach_authorization = self.ach_authorization  # Keep for backward compat
        retry_txn.loan = self.loan
        retry_txn.customer = self.customer
        retry_txn.amount = self.amount
        retry_txn.status = "Scheduled"
        retry_txn.scheduled_date = today()
        retry_txn.retry_attempt = self.retry_attempt + 1
        retry_txn.max_retries = self.max_retries
        retry_txn.original_transaction = self.original_transaction or self.name
        retry_txn.insert()

        self.next_retry_date = None
        self.save()

        return retry_txn

    def create_payment_entry(self):
        """Create ERPNext Payment Entry for successful transaction."""
        from dcr.dcr.doctype.ach_settings.ach_settings import get_ach_settings

        try:
            loan = frappe.get_doc("Loan", self.loan)
            settings = get_ach_settings()

            existing = frappe.db.exists(
                "Payment Entry",
                {"reference_no": self.name, "docstatus": ["!=", 2]}
            )
            if existing:
                return frappe.get_doc("Payment Entry", existing)

            payment_entry = frappe.new_doc("Payment Entry")
            payment_entry.payment_type = "Receive"
            payment_entry.party_type = "Customer"
            payment_entry.party = self.customer
            payment_entry.paid_amount = self.amount
            payment_entry.received_amount = self.amount
            payment_entry.reference_no = self.name
            payment_entry.reference_date = getdate(self.completed_date)
            payment_entry.company = loan.company

            if settings.ach_clearing_account:
                payment_entry.paid_to = settings.ach_clearing_account
            else:
                payment_entry.paid_to = frappe.get_cached_value(
                    "Company", loan.company, "default_cash_account"
                ) or frappe.get_cached_value(
                    "Company", loan.company, "default_bank_account"
                )

            if settings.mode_of_payment:
                payment_entry.mode_of_payment = settings.mode_of_payment

            payment_entry.append("references", {
                "reference_doctype": "Loan",
                "reference_name": self.loan,
                "allocated_amount": self.amount
            })

            payment_entry.insert()
            payment_entry.submit()

            return payment_entry

        except Exception as e:
            frappe.log_error(
                f"Failed to create Payment Entry for ACH Transaction {self.name}: {str(e)}",
                "ACH Payment Entry Creation"
            )
            return None

    def send_notification(self, notification_type):
        """Send notification based on transaction status."""
        from dcr.dcr.doctype.ach_settings.ach_settings import get_ach_settings
        settings = get_ach_settings()

        should_send = False
        if notification_type == "success" and settings.send_success_notification:
            should_send = True
        elif notification_type == "failure" and settings.send_failure_notification:
            should_send = True
        elif notification_type == "upcoming" and settings.send_upcoming_debit_notification:
            should_send = True

        if not should_send:
            return

        try:
            customer_email = frappe.db.get_value("Customer", self.customer, "email_id")
            if not customer_email:
                return

            subject_map = {
                "success": f"Payment Successful - {self.amount}",
                "failure": f"Payment Failed - {self.amount}",
                "upcoming": f"Upcoming Payment - {self.amount}",
            }

            template_map = {
                "success": "ach_payment_success",
                "failure": "ach_payment_failure",
                "upcoming": "ach_payment_upcoming",
            }

            frappe.sendmail(
                recipients=[customer_email],
                subject=subject_map.get(notification_type),
                template=template_map.get(notification_type),
                args={
                    "customer": self.customer,
                    "amount": self.amount,
                    "loan": self.loan,
                    "transaction": self.name,
                    "failure_reason": self.failure_reason,
                    "scheduled_date": self.scheduled_date,
                },
                now=True
            )

            self.notification_sent = 1
            self.save()

        except Exception as e:
            frappe.log_error(
                f"Failed to send notification for ACH Transaction {self.name}: {str(e)}",
                "ACH Notification"
            )
