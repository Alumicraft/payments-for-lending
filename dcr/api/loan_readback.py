"""Read-only funding display for invoice-backed floorplan loans."""
from decimal import Decimal

import frappe


def show_posted_funding(doc, method=None):
    if (doc.get('docstatus') != 1 or not doc.get('original_financed_principal')
            or not doc.get('home_build_request')):
        return
    info = doc.get_onload('dashboard_info')
    if not info:
        return
    funding = frappe.get_all('Loan Disbursement',
        filters={'against_loan': doc.get('name'), 'docstatus': 1},
        fields=['disbursed_amount'])
    info['total_principal'] = float(sum(
        (Decimal(str(row.disbursed_amount or 0)) for row in funding), Decimal(0)))
    doc.set_onload('dashboard_info', info)
