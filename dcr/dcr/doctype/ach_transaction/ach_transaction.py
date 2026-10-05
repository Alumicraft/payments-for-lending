# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, add_days, getdate, today, flt
from dcr.api.notification_queue import queue_notification

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

        from dcr.dcr.doctype.ach_settings.ach_settings import loan_is_in_ach_scope
        if not loan_is_in_ach_scope(self.loan):
            frappe.throw(_("This loan is outside the configured ACH pilot scope"))
        status = self._get_account_status()
        if status != "Active":
            frappe.throw(_("Payment account is not active"))

        token, token_source = self._get_token_and_source()
        if not token:
            frappe.throw(_("No payment token found on the payment account"))

        from dcr.api.achq_integration import ACHQClient, get_customer_billing_details
        client = ACHQClient()
        customer_name = frappe.db.get_value("Customer", self.customer, "customer_name")
        billing = get_customer_billing_details(self.customer)
        account, _ = self._get_payment_account()
        customer_ip = account.get("custom_authorization_ip" if self.bank_account else "authorization_ip") if account else None
        # Missing local data must remain Scheduled, not an uncertain remote debit.
        client.payment_parameters(self.amount, token, customer_name, f"Loan payment for {self.loan}",
            self.name, customer_ip=customer_ip, token_source=token_source, billing=billing)

        # Persist admission before the provider call. A crash or lost response must
        # never leave the debit eligible for another submission.
        frappe.db.get_value("ACH Transaction", self.name, "name", for_update=True)
        self.reload()
        if self.status != "Scheduled":
            frappe.throw(_("This debit has already been admitted"))
        self.status = "Outcome Unknown"
        self.initiated_date = now_datetime()
        self.failure_reason = "Submission admitted; awaiting provider confirmation"
        self.save()
        frappe.db.commit()

        result = client.create_payment(
            amount=self.amount,
            token=token,
            customer_name=customer_name,
            description=f"Loan payment for {self.loan}",
            txn_id=self.name,
            token_source=token_source,
            customer_ip=customer_ip,
            billing=billing
        )

        frappe.db.get_value("ACH Transaction", self.name, "name", for_update=True)
        self.reload()
        # A webhook may already have advanced this transaction while we waited.
        if self.status != "Outcome Unknown":
            return self.status not in ("Failed", "Returned", "Cancelled")
        if result.get("success"):
            self.status = "Initiated"
            self.achq_transaction_id = result.get("transaction_id")
            self.achq_reference_kind = "TransAct Reference"
            self.achq_status = result.get("status")
            self.failure_reason = None
            self.settlement_date = add_days(today(), 5)
            self.save()
            return True
        else:
            self.status = "Outcome Unknown" if result.get("outcome_unknown") else "Failed"
            self.failure_code = result.get("error_code")
            self.failure_reason = result.get("error_message")
            self.save()
            return False

    def mark_success(self, achq_status=None):
        """Record settlement only after Lending has posted the repayment."""
        if self.status in ("Returned", "Reversal Pending", "Cancelled"):
            return False  # Do not let a delayed settlement event undo a return.
        if self.status == "Success" and self.loan_repayment:
            return True
        self.completed_date = self.completed_date or now_datetime()
        if achq_status:
            self.achq_status = achq_status
        repayment = self.create_loan_repayment()
        if not repayment:
            self.status = "Accounting Pending"
            self.next_retry_date = None
            self.save()
            return False
        self.loan_repayment = repayment.name
        self.accounting_error = None
        self.status = "Success"
        self.next_retry_date = None
        self.save()
        self.send_notification("success")
        return True

    def mark_failed(self, failure_code=None, failure_reason=None, return_code=None, returned=False):
        """A late return needs accounting reversal before any retry is admitted."""
        if self.status in ("Returned", "Reversal Pending", "Cancelled"):
            return True
        posted = bool(self.loan_repayment or self.payment_entry) or self.status in ("Success", "Accounting Pending")
        self.status = "Reversal Pending" if posted else ("Returned" if returned or return_code else "Failed")
        self.return_code = return_code
        self.failure_code = failure_code
        self.failure_reason = failure_reason
        self.completed_date = now_datetime()
        self.next_retry_date = None
        if posted:
            self.accounting_error = "Provider returned this payment. Review and reverse any posted repayment/payment entry before retrying."
        self.save()
        if not posted and self.should_retry(return_code):
            self.schedule_retry()
        self.send_notification("failure")
        return True

    def cancel_transaction(self, reason=None):
        """Cancel the transaction if still scheduled or initiated."""
        frappe.db.get_value("ACH Transaction", self.name, "name", for_update=True)
        self.reload()
        if self.status not in ("Scheduled", "Initiated"):
            frappe.throw(_("Only scheduled or initiated transactions can be cancelled"))

        if self.status == "Initiated" and (not self.achq_transaction_id or self.achq_reference_kind != "TransAct Reference"):
            frappe.throw(_("Provider reference needs verification; reconcile the payment before cancelling"))
        if self.status == "Initiated" and self.achq_transaction_id:
            from dcr.api.achq_integration import ACHQClient
            client = ACHQClient(allow_disabled=True)
            result = client.cancel_payment(self.achq_transaction_id)
            if not result.get("success"):
                frappe.log_error(
                    f"Failed to cancel ACHQ transaction {self.achq_transaction_id}: "
                    f"{result.get('error_message')}",
                    "ACH Transaction Cancellation"
                )
                frappe.throw(_("ACHQ did not confirm cancellation. The transaction remains initiated; reconcile its provider status."))

        self.status = "Cancelled"
        self.failure_reason = reason or "Cancelled by user"
        self.save()

        self.add_comment("Comment", f"Transaction cancelled: {reason or 'No reason provided'}")
        return True

    def should_retry(self, return_code):
        """Determine if the transaction should be retried based on return code."""
        if self.retry_attempt >= min(self.max_retries or 0, 2):
            return False
        return return_code in RETRYABLE_RETURN_CODES

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
        frappe.db.get_value("ACH Transaction", self.name, "name", for_update=True)
        self.reload()
        if self.status != "Returned" or not self.should_retry(self.return_code):
            frappe.throw(_("Only an eligible returned payment can be retried"))
        root = self.original_transaction or self.name
        existing = frappe.db.exists("ACH Transaction", {
            "original_transaction": root, "retry_attempt": self.retry_attempt + 1
        })
        if existing:
            self.next_retry_date = None
            self.save()
            return frappe.get_doc("ACH Transaction", existing)

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
        retry_txn.payment_due_date = self.payment_due_date
        retry_txn.retry_attempt = self.retry_attempt + 1
        retry_txn.max_retries = self.max_retries
        retry_txn.original_transaction = self.original_transaction or self.name
        retry_txn.insert()

        self.next_retry_date = None
        self.save()

        return retry_txn

    def create_loan_repayment(self):
        """Lending owns allocation and GL posting; do not also book a Payment Entry."""
        from dcr.dcr.doctype.ach_settings.ach_settings import get_ach_settings

        savepoint = "ach_repayment"
        frappe.db.savepoint(savepoint)
        try:
            # Legacy payments require deliberate reconciliation, not a second GL receipt.
            if self.payment_entry or frappe.db.exists("Payment Entry", {
                "reference_no": self.name, "docstatus": ["!=", 2]
            }):
                raise ValueError("Legacy Payment Entry exists; reconcile it before creating a Loan Repayment")
            existing = self.loan_repayment or frappe.db.exists("Loan Repayment", {
                "reference_number": self.name, "docstatus": ["!=", 2]
            })
            if existing:
                repayment = frappe.get_doc("Loan Repayment", existing)
                if repayment.against_loan != self.loan or round(flt(repayment.amount_paid), 2) != round(flt(self.amount), 2):
                    raise ValueError("Existing repayment does not match this ACH loan and amount")
            else:
                loan = frappe.get_doc("Loan", self.loan)
                settings = get_ach_settings()
                if not settings.ach_clearing_account:
                    raise ValueError("Configure ACH Clearing Account before posting settlement")
                repayment = frappe.new_doc("Loan Repayment")
                repayment.against_loan = self.loan
                repayment.applicant_type = loan.applicant_type
                repayment.applicant = loan.applicant
                repayment.company = loan.company
                repayment.loan_product = loan.loan_product
                repayment.amount_paid = self.amount
                repayment.repayment_type = "Normal Repayment"
                repayment.posting_date = self.completed_date
                repayment.value_date = self.completed_date
                repayment.due_date = self.payment_due_date
                repayment.reference_number = self.name
                repayment.reference_date = getdate(self.completed_date)
                repayment.payment_account = settings.ach_clearing_account
                repayment.mode_of_payment = settings.mode_of_payment
                # This authenticated provider event posts only the matched ACH record.
                repayment.insert(ignore_permissions=True)
            if repayment.docstatus == 0:
                repayment.flags.ignore_permissions = True
                repayment.submit()
            if repayment.docstatus != 1:
                raise ValueError("Loan Repayment is not submitted")
            return repayment
        except Exception as error:
            frappe.db.rollback(save_point=savepoint)
            self.accounting_error = str(error)
            frappe.log_error(f"ACH {self.name}: {error}", "ACH Repayment Posting")
            return None

    def send_notification(self, notification_type):
        """Send notification based on transaction status."""
        from dcr.dcr.doctype.ach_settings.ach_settings import get_ach_settings
        settings = get_ach_settings()

        notification_field = f"{notification_type}_notification_sent"
        if self.get(notification_field):
            return
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

            queue = queue_notification(
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
                delayed=True
            )

            if not queue:
                raise ValueError("No outgoing email queue was created")
            self.set(notification_field, 1)
            self.notification_sent = 1
            self.save()

        except Exception as e:
            frappe.log_error(
                f"Failed to send notification for ACH Transaction {self.name}: {str(e)}",
                "ACH Notification"
            )
