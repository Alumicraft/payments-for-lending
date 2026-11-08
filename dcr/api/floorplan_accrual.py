"""Actual principal balances for invoice-backed DCR floorplan interest."""

from contextlib import contextmanager, nullcontext
from datetime import timedelta
from decimal import Decimal

import frappe
from frappe.utils import getdate

from dcr.api.floorplan_terms import product_terms
from dcr.lending_rules import elapsed_floorplan_interest, floorplan_interval_interest, principal_on_day


def floorplan_loan(name):
    loan = frappe.get_doc('Loan', name)
    if not loan.get('original_financed_principal') or not loan.get('home_build_request'):
        return None
    if product_terms(loan.loan_product).get('schedule_type') != 'Interest Only Then Percent Principal':
        return None
    return loan


def principal_events(loan):
    if any(loan.get(field) for field in (
        'debit_adjustment_amount', 'credit_adjustment_amount', 'written_off_amount'
    )):
        frappe.throw('Dated floorplan interest requires review of this loan\'s principal adjustments.')
    funding = frappe.get_all('Loan Disbursement',
        filters={'against_loan': loan.name, 'docstatus': 1},
        fields=['disbursement_date', 'disbursed_amount'])
    receipts = frappe.get_all('Loan Repayment',
        filters={'against_loan': loan.name, 'docstatus': 1},
        fields=['value_date', 'principal_amount_paid'])
    events = [(row.disbursement_date, row.disbursed_amount) for row in funding]
    events.extend((row.value_date, -float(row.principal_amount_paid or 0)) for row in receipts)
    if not funding:
        frappe.throw('Dated floorplan interest requires a submitted funding record.')
    return events


def projected_interest(loan, value_date):
    return interest_projection(loan, value_date)[0]


def interest_projection(loan, value_date):
    end = getdate(value_date)
    if frappe.db.get_value('Company', loan.company, 'loan_accrual_frequency') != 'Daily':
        frappe.throw('DCR floorplan interest requires Daily loan accrual frequency.')
    events = principal_events(loan)
    latest = frappe.get_all('Loan Interest Accrual', filters={
        'loan': loan.name, 'docstatus': 1, 'interest_type': 'Normal Interest',
        'posting_date': ['<', str(end)],
    }, fields=['posting_date'], order_by='posting_date desc', limit_page_length=1)
    start = (getdate(latest[0].posting_date) + timedelta(days=1) if latest
             else min(getdate(day) for day, amount in events if float(amount) > 0))
    return (floorplan_interval_interest(events, first_payment_date(loan), start, end, loan.rate_of_interest),
            elapsed_floorplan_interest(events, start, end, loan.rate_of_interest))


def first_payment_date(loan):
    first = (frappe.db.get_value('Loan Application', loan.loan_application, 'first_payment_date')
             if loan.get('loan_application') else None)
    first = first or loan.get('repayment_start_date')
    if not first:
        frappe.throw('The original first payment date is required for floorplan interest rounding.')
    return first


def extra_payment_interest(name, start, end, balance_after_payment):
    loan = floorplan_loan(name)
    if not loan:
        return None
    events = principal_events(loan)
    events.append((start, Decimal(str(balance_after_payment)) - principal_on_day(events, start)))
    return float(floorplan_interval_interest(events, first_payment_date(loan), start, end,
                                            loan.rate_of_interest))


def populate_repayment_loan_type(doc):
    if doc.repayment_type not in ('Pre Payment', 'Loan Closure') or doc.get('is_imported'):
        return
    loan = floorplan_loan(doc.against_loan)
    if loan:
        doc.is_term_loan = loan.is_term_loan
        doc.repayment_schedule_type = loan.repayment_schedule_type


def scheduled_interest_due(name, demand_date):
    """Demand earned interest once, including unpaid-principal and waiver effects."""
    loan = floorplan_loan(name)
    if not loan:
        return None
    end = str(getdate(demand_date))
    accrued = frappe.get_all('Loan Interest Accrual', filters={
        'loan': name, 'docstatus': 1, 'interest_type': 'Normal Interest',
        'posting_date': ['<', end],
    }, fields=[{'SUM': 'interest_amount', 'as': 'amount'}])
    demanded = frappe.get_all('Loan Demand', filters={
        'loan': name, 'docstatus': 1, 'demand_subtype': 'Interest',
        'demand_date': ['<=', end],
    }, fields=[{'SUM': 'demand_amount', 'as': 'amount'}])
    booked = Decimal(str(accrued[0].amount or 0))
    billed = Decimal(str(demanded[0].amount or 0))
    return max(Decimal(0), booked + projected_interest(loan, end) - billed)


def adjust_closure_amounts(name, value_date, amounts):
    loan = floorplan_loan(name)
    if not loan:
        return
    projected = float(projected_interest(loan, value_date))
    difference = projected - float(amounts.get('unaccrued_interest') or 0)
    amounts['unaccrued_interest'] = projected
    amounts['interest_amount'] = round(float(amounts.get('interest_amount') or 0) + difference, 2)
    amounts['payable_amount'] = round(float(amounts.get('payable_amount') or 0) + difference, 2)


@frappe.whitelist()
def calculate_amounts(against_loan, posting_date, payment_type=None, with_loan_details=False,
                      charges=None, loan_disbursement=None, for_update=False):
    from lending.loan_management.doctype.loan_repayment.loan_repayment import (
        calculate_amounts as native_calculate,
    )

    with (actual_principal_accruals() if payment_type in ('Advance Payment', 'Pre Payment')
          else nullcontext()):
        result = native_calculate(against_loan, posting_date, payment_type=payment_type,
            with_loan_details=with_loan_details, charges=charges,
            loan_disbursement=loan_disbursement, for_update=for_update)
    if payment_type == 'Loan Closure':
        amounts = result['amounts'] if with_loan_details else result
        adjust_closure_amounts(against_loan, posting_date, amounts)
    elif payment_type in ('Advance Payment', 'Pre Payment'):
        loan = floorplan_loan(against_loan)
        if loan:
            amounts = result['amounts'] if with_loan_details else result
            amounts['unaccrued_interest'] = float(projected_interest(loan, posting_date))
    return result


@contextmanager
def actual_principal_accruals():
    from lending.loan_management.doctype.loan_interest_accrual import loan_interest_accrual as native

    original = native.get_principal_amount_for_term_loan
    original_entry = native.make_loan_interest_accrual_entry
    schedules = {}

    def actual_balance(schedule, day):
        if schedule not in schedules:
            name = frappe.db.get_value('Loan Repayment Schedule', schedule, 'loan')
            loan = floorplan_loan(name) if name else None
            schedules[schedule] = principal_events(loan) if loan else None
        events = schedules[schedule]
        return float(principal_on_day(events, day)) if events is not None else original(schedule, day)

    def rounded_entry(loan, base_amount, interest_amount, process_loan_interest, start_date,
                      posting_date, accrual_type, interest_type, rate_of_interest, loan_demand=None,
                      loan_repayment_schedule=None, additional_interest=0, accrual_date=None,
                      loan_repayment_schedule_detail=None, loan_disbursement=None, is_imported=False):
        if interest_type == 'Normal Interest' and not is_imported:
            contract = floorplan_loan(loan)
            if contract:
                events = principal_events(contract)
                base_amount = float(principal_on_day(events, posting_date))
                interest_amount = float(floorplan_interval_interest(events, first_payment_date(contract),
                    start_date, getdate(posting_date)+timedelta(days=1), rate_of_interest))
        return original_entry(loan, base_amount, interest_amount, process_loan_interest, start_date,
            posting_date, accrual_type, interest_type, rate_of_interest, loan_demand=loan_demand,
            loan_repayment_schedule=loan_repayment_schedule, additional_interest=additional_interest,
            accrual_date=accrual_date, loan_repayment_schedule_detail=loan_repayment_schedule_detail,
            loan_disbursement=loan_disbursement, is_imported=is_imported)

    native.get_principal_amount_for_term_loan = actual_balance
    native.make_loan_interest_accrual_entry = rounded_entry
    try:
        yield
    finally:
        native.get_principal_amount_for_term_loan = original
        native.make_loan_interest_accrual_entry = original_entry
