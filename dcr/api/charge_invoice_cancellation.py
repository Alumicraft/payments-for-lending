"""Cancel generated charge demands with their DCR invoice, without a new return."""
import frappe

from dcr.api.floorplan_accrual import floorplan_loan


def owns_charge_demands(doc):
    return bool(doc.get('loan') and not doc.get('is_return')
                and not doc.get('loan_disbursement') and floorplan_loan(doc.loan))


def onload(doc, method=None):
    doc.set_onload('dcr_cancel_charge_demands_with_invoice', owns_charge_demands(doc))


def before_cancel(doc, method=None):
    if not owns_charge_demands(doc):
        return
    demands = frappe.get_all('Loan Demand', filters={
        'sales_invoice': doc.name, 'loan': doc.loan,
        'demand_type': 'Charges', 'docstatus': 1,
    }, fields=['paid_amount', 'waived_amount'])
    if any(row.paid_amount or row.waived_amount for row in demands):
        frappe.throw('Cancel the associated charge payments and waivers before cancelling this fee invoice.')


def on_cancel(doc, method=None):
    if not owns_charge_demands(doc):
        return
    for name in frappe.get_all('Loan Demand', filters={
        'sales_invoice': doc.name, 'loan': doc.loan,
        'demand_type': 'Charges', 'docstatus': 1,
    }, pluck='name', order_by='name'):
        demand = frappe.get_doc('Loan Demand', name)
        demand.flags.ignore_links = True
        demand.cancel()
