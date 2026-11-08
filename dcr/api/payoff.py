"""Read-only dated amounts for the staff flooring payoff print."""

import frappe
from frappe.utils import getdate, today

from dcr.api.floorplan_accrual import calculate_amounts


def flooring_payoff_quote(name, quote_date=None):
    loan = frappe.get_doc('Loan', name)
    loan.check_permission('read')
    if loan.docstatus != 1 or loan.status not in ('Disbursed', 'Partially Disbursed', 'Active'):
        return dict(available=False, reason='A payoff quote requires an open, funded loan.')

    day = getdate(quote_date or today())
    if loan.get('disbursement_date') and day < getdate(loan.disbursement_date):
        return dict(available=False, reason='The payoff date must be on or after funding.')
    latest = frappe.get_all('Loan Repayment', filters={
        'against_loan': name, 'docstatus': 1,
    }, fields=['value_date'], order_by='value_date desc', limit_page_length=1)
    if latest and day < getdate(latest[0].value_date):
        return dict(available=False,
                    reason='The payoff date must be on or after the latest submitted repayment.')

    amounts = calculate_amounts(name, str(day), payment_type='Loan Closure')
    return dict(available=True, date=str(day),
                principal=amounts['payable_principal_amount'],
                interest=amounts['interest_amount'], penalty=amounts['penalty_amount'],
                charges=amounts['total_charges_payable'], total=amounts['payable_amount'])
