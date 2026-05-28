# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
Scheduled Tasks for ACH Processing

Daily tasks:
- process_upcoming_payments: Create transactions for upcoming loan payments
- initiate_scheduled_transactions: Send scheduled transactions to ACHQ
- process_retry_transactions: Retry failed transactions

Hourly tasks:
- check_pending_transactions: Poll ACHQ for status updates (backup to webhooks)
"""

import frappe
from frappe.utils import today, add_days, getdate, get_time, nowtime


def is_ach_enabled():
    """Check if ACH autopay is enabled."""
    try:
        settings = frappe.get_single("ACH Settings")
        return settings.enable_ach_autopay
    except Exception:
        return False


def process_upcoming_payments():
    """
    Find loans with payments due soon and create ACH Transactions.

    This runs daily and:
    1. Finds active loans that have a valid payment account (loan-specific or customer default)
    2. Checks for upcoming payments based on advance_notification_days
    3. Creates ACH Transactions for each upcoming payment
    4. Sends advance notification to customers
    """
    if not is_ach_enabled():
        return

    from dcr.api.bank_account_ach import get_loan_payment_account

    settings = frappe.get_single("ACH Settings")
    notification_days = settings.advance_notification_days
    initiation_days = settings.days_before_due_to_initiate

    target_date = add_days(today(), notification_days)

    frappe.logger().info(f"Processing upcoming payments for due date: {target_date}")

    active_loans = frappe.get_all(
        "Loan",
        filters={
            "status": ["in", ["Disbursed", "Partially Disbursed", "Active"]]
        },
        fields=["name", "applicant"]
    )

    for loan_data in active_loans:
        try:
            account = get_loan_payment_account(loan_data.name)

            if not account:
                continue

            if account.get("custom_ach_status") != "Active":
                continue

            process_loan_payment(loan_data, account, target_date, initiation_days)
        except Exception as e:
            frappe.log_error(
                f"Error processing loan {loan_data.name}: {str(e)}",
                "ACH Process Upcoming Payments"
            )

    frappe.db.commit()


def process_loan_payment(loan_data, account, target_date, initiation_days):
    """
    Process a single loan for upcoming payment.

    Args:
        loan_data: Loan dict with name and applicant
        account: Bank Account document (resolved for this loan)
        target_date: The due date we're looking for
        initiation_days: Days before due to schedule initiation
    """
    loan = frappe.get_doc("Loan", loan_data.name)

    next_payment_date, next_payment_amount = get_next_unpaid_repayment(loan)

    if not next_payment_date:
        return

    if next_payment_date != getdate(target_date):
        return

    if not next_payment_amount or next_payment_amount <= 0:
        return

    # Check if transaction already exists for this payment
    existing = frappe.db.exists(
        "ACH Transaction",
        {
            "loan": loan.name,
            "scheduled_date": [">=", add_days(target_date, -initiation_days)],
            "status": ["not in", ["Cancelled", "Failed", "Returned"]]
        }
    )
    if existing:
        return

    scheduled_date = add_days(target_date, -initiation_days)

    txn = frappe.new_doc("ACH Transaction")
    txn.bank_account = account.name
    txn.loan = loan.name
    txn.customer = loan.applicant
    txn.amount = next_payment_amount
    txn.status = "Scheduled"
    txn.scheduled_date = scheduled_date
    txn.insert()

    frappe.logger().info(
        f"Created ACH Transaction {txn.name} for loan {loan.name}, "
        f"amount {next_payment_amount}, scheduled for {scheduled_date}"
    )

    txn.send_notification("upcoming")


def get_next_unpaid_repayment(loan):
    """Get next unpaid repayment from loan schedule.

    Frappe Lending v15 doesn't have an is_paid field on repayment schedule rows.
    Instead, we query submitted Loan Repayment records to determine which
    schedule rows have been paid.
    """
    if not hasattr(loan, 'repayment_schedule') or not loan.repayment_schedule:
        return None, None

    paid_dates = frappe.get_all("Loan Repayment",
        filters={"against_loan": loan.name, "docstatus": 1},
        pluck="posting_date")
    paid_dates = set(getdate(d) for d in paid_dates)

    for row in loan.repayment_schedule:
        row_date = getdate(row.payment_date)
        if row_date >= getdate(today()) and row_date not in paid_dates:
            return row_date, row.total_payment
    return None, None


def initiate_scheduled_transactions():
    """
    Initiate ACH Transactions that are scheduled for today.

    This runs daily and:
    1. Finds transactions with status=Scheduled and scheduled_date<=today
    2. Checks if we're before the cutoff time
    3. Initiates each transaction via ACHQ API
    """
    if not is_ach_enabled():
        return

    settings = frappe.get_single("ACH Settings")

    cutoff_time = settings.cutoff_time
    if cutoff_time:
        current_time = get_time(nowtime())
        if current_time > cutoff_time:
            frappe.logger().info(
                f"Past cutoff time ({cutoff_time}), skipping initiation until tomorrow"
            )
            return

    transactions = frappe.get_all(
        "ACH Transaction",
        filters={
            "status": "Scheduled",
            "scheduled_date": ["<=", today()]
        },
        pluck="name"
    )

    frappe.logger().info(f"Found {len(transactions)} transactions to initiate")

    for txn_name in transactions:
        try:
            txn = frappe.get_doc("ACH Transaction", txn_name)

            # Verify payment account is still active
            status = txn._get_account_status()
            if status != "Active":
                account_ref = txn.bank_account or txn.ach_authorization
                frappe.logger().warning(
                    f"Skipping transaction {txn_name}: payment account {account_ref} is {status}"
                )
                continue

            success = txn.initiate()
            if success:
                frappe.logger().info(f"Initiated transaction {txn_name}")
            else:
                frappe.logger().warning(f"Failed to initiate transaction {txn_name}")

        except Exception as e:
            frappe.log_error(
                f"Error initiating transaction {txn_name}: {str(e)}",
                "ACH Initiate Transactions"
            )

    frappe.db.commit()


def process_retry_transactions():
    """
    Process transactions that are due for retry.

    This runs daily and:
    1. Finds failed/returned transactions with next_retry_date<=today
    2. Verifies retry attempts haven't exceeded max
    3. Creates new retry transactions
    """
    if not is_ach_enabled():
        return

    transactions = frappe.get_all(
        "ACH Transaction",
        filters=[
            ["status", "in", ["Failed", "Returned"]],
            ["next_retry_date", "<=", today()],
            ["next_retry_date", "is", "set"]
        ],
        fields=["name", "retry_attempt", "max_retries", "bank_account", "ach_authorization"]
    )

    frappe.logger().info(f"Found {len(transactions)} transactions for retry")

    for txn_data in transactions:
        try:
            if txn_data.retry_attempt >= txn_data.max_retries:
                continue

            # Check payment account is still active
            if txn_data.bank_account:
                acct_status = frappe.db.get_value("Bank Account", txn_data.bank_account, "custom_ach_status")
            elif txn_data.ach_authorization:
                acct_status = frappe.db.get_value("ACH Authorization", txn_data.ach_authorization, "status")
            else:
                acct_status = None

            if acct_status != "Active":
                frappe.logger().warning(
                    f"Skipping retry for {txn_data.name}: payment account is {acct_status}"
                )
                frappe.db.set_value("ACH Transaction", txn_data.name, "next_retry_date", None)
                continue

            txn = frappe.get_doc("ACH Transaction", txn_data.name)
            retry_txn = txn.create_retry_transaction()

            frappe.logger().info(
                f"Created retry transaction {retry_txn.name} for {txn_data.name}"
            )

        except Exception as e:
            frappe.log_error(
                f"Error creating retry for {txn_data.name}: {str(e)}",
                "ACH Retry Transactions"
            )

    frappe.db.commit()


def check_pending_transactions():
    """
    Poll ACHQ for status updates on pending transactions.

    This is a backup to webhooks and runs hourly:
    1. Queries ACHQ for all status changes today and yesterday
    2. Matches transactions by reference ID
    3. Updates transactions if status has changed
    """
    if not is_ach_enabled():
        return

    from dcr.api.achq_integration import ACHQClient

    try:
        client = ACHQClient()
    except Exception as e:
        frappe.log_error(
            f"Failed to initialize ACHQ client: {str(e)}",
            "ACH Check Pending"
        )
        return

    dates_to_check = [today(), add_days(today(), -1)]

    for check_date in dates_to_check:
        try:
            result = client.get_status_by_date(check_date)

            if not result.get("success"):
                frappe.logger().warning(
                    f"Failed to get status for {check_date}: {result.get('error_message')}"
                )
                continue

            transactions = result.get("transactions", [])
            frappe.logger().info(f"Got {len(transactions)} status updates for {check_date}")

            for achq_txn in transactions:
                process_achq_status_update(achq_txn)

        except Exception as e:
            frappe.log_error(
                f"Error checking status for {check_date}: {str(e)}",
                "ACH Check Pending"
            )

    frappe.db.commit()


def process_achq_status_update(achq_txn):
    """
    Process a single ACHQ transaction status update.

    Args:
        achq_txn: Transaction dict from ACHQ status query
    """
    from dcr.api.achq_integration import ACHQ_STATUS_MAP

    achq_transaction_id = achq_txn.get("TransactionID")
    merchant_ref_id = achq_txn.get("Merchant_ReferenceID")

    txn_name = None

    if merchant_ref_id and frappe.db.exists("ACH Transaction", merchant_ref_id):
        txn_name = merchant_ref_id
    elif achq_transaction_id:
        txn_name = frappe.db.get_value(
            "ACH Transaction",
            {"achq_transaction_id": achq_transaction_id},
            "name"
        )

    if not txn_name:
        return

    txn = frappe.get_doc("ACH Transaction", txn_name)

    if txn.status in ("Success", "Cancelled"):
        return

    achq_status = achq_txn.get("PaymentStatus", "")
    mapped_status = ACHQ_STATUS_MAP.get(achq_status)

    if not mapped_status:
        if txn.achq_status != achq_status:
            txn.achq_status = achq_status
            txn.save()
        return

    try:
        if mapped_status == "Success" and txn.status != "Success":
            txn.mark_success(achq_status=achq_status)
            frappe.logger().info(f"Transaction {txn_name} marked as success")

        elif mapped_status == "Returned" and txn.status not in ("Returned", "Failed"):
            txn.mark_failed(
                return_code=achq_txn.get("ReturnCode"),
                failure_reason=achq_txn.get("ReturnDescription"),
            )
            frappe.logger().info(f"Transaction {txn_name} marked as returned")

        elif mapped_status == "Processing" and txn.status == "Initiated":
            txn.status = "Processing"
            txn.achq_status = achq_status
            txn.save()

        elif mapped_status == "Cancelled" and txn.status not in ("Cancelled", "Success"):
            txn.status = "Cancelled"
            txn.achq_status = achq_status
            txn.save()

        elif mapped_status == "Failed" and txn.status not in ("Failed", "Returned", "Success"):
            txn.mark_failed(
                failure_code=achq_txn.get("ResponseCode"),
                failure_reason=achq_txn.get("Description", "Payment failed"),
            )
            frappe.logger().info(f"Transaction {txn_name} marked as failed")

    except Exception as e:
        frappe.log_error(
            f"Error updating transaction {txn_name}: {str(e)}",
            "ACH Status Update"
        )
