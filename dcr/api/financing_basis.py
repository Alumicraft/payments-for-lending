"""The invoice and financial terms actually reviewed by the dealer."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

import frappe
from dcr.api.floorplan_terms import product_terms


def money(value):
    try:
        amount = Decimal(str(value or 0))
        if not amount.is_finite():
            raise ValueError('Financed amounts must be finite')
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise ValueError('Invalid financed amount') from error


def interest_rate(value):
    rate = Decimal(str(value or 0))
    if not rate.is_finite() or rate < 0:
        frappe.throw('Interest rate must be finite and non-negative.')
    return rate.normalize()


def financial_snapshot(application, *, require_invoice=False, check_permission=True):
    """Resolve a quote for early review, or a submitted final invoice for funding.

    Purchase Invoice total includes freight/taxes/fees entered on it.
    financed_dcr_fees contains ONLY additional financed fees outside that total.
    Supplier invoice date is bill_date; posting_date is the fallback when the
    supplier date is absent. Accounting entry date remains a separate concern.
    """
    invoice_name = application.get('financed_invoice')
    if require_invoice and not invoice_name:
        frappe.throw('Select the final Funding Invoice before funding this loan.')
    invoice = frappe.get_doc('Purchase Invoice', invoice_name) if invoice_name else None
    company = application.get('company')
    company_currency = frappe.db.get_value('Company', company, 'default_currency')
    terms = product_terms(application.get('loan_product'),application.get('rate_of_interest'))
    if terms['schedule_type'] != 'Interest Only Then Percent Principal':
        frappe.throw('Select a DCR floorplan loan product before reviewing the Flooring Packet.')
    if interest_rate(terms['annual_rate']) != interest_rate(application.get('rate_of_interest')):
        frappe.throw('Application interest rate must match the configured product contract rate before reviewing its packet.')
    fees = money(application.get('financed_dcr_fees'))
    if fees < 0:
        frappe.throw('Additional financed DCR fees cannot be negative.')
    if invoice:
        if check_permission:
            invoice.check_permission('read')
        if invoice.docstatus != 1 or invoice.get('is_return'):
            frappe.throw('Funding Invoice must be a submitted purchase invoice, not a return.')
        if invoice.company != company or invoice.currency != company_currency:
            frappe.throw('Funding Invoice must use the loan company and company currency.')
        request_name = invoice.get('home_build_request') or invoice.get('custom_home_build_request')
        if not request_name or request_name != application.get('home_build_request'):
            frappe.throw('Funding Invoice must belong to this Home Build Request.')
        request = frappe.get_doc('Home Build Request', request_name)
        if request.customer != application.applicant or request.factory != invoice.supplier:
            frappe.throw('Funding Invoice must match this dealer and assigned factory.')
        total = money(invoice.get('rounded_total') if invoice.get('rounded_total') and
                      not invoice.get('disable_rounded_total') else invoice.grand_total)
        invoice_date = date.fromisoformat(str(invoice.get('bill_date') or invoice.posting_date)[:10])
    else:
        total = money(application.get('loan_amount'))
        # An early quote is already the requested all-in principal; it is not
        # an invoice total to which the separate fee field should be added.
        fees = Decimal(0)
        invoice_date = None
    amount = total + fees
    if amount <= 0:
        frappe.throw('Financed principal must be greater than zero.')
    first_payment_date = application.get('first_payment_date')
    if first_payment_date:
        first_payment_date = date.fromisoformat(str(first_payment_date)[:10])
        if invoice_date and first_payment_date < invoice_date:
            frappe.throw('First Payment Date cannot precede the invoice/funding date.')
    return dict(version=1, source='invoice' if invoice else 'quote',
                invoice=invoice_name or None, invoice_date=str(invoice_date) if invoice_date else None,
                company=company, currency=company_currency, customer=application.applicant,
                home_build_request=application.get('home_build_request'),
                invoice_total=str(total), additional_financed_fees=str(fees), principal=str(amount),
                annual_interest_rate=str(interest_rate(application.get('rate_of_interest'))),
                first_payment_date=str(first_payment_date) if first_payment_date else None,
                monthly_insurance_amount=str(money(application.get('monthly_insurance_amount'))),
                loan_product=application.get('loan_product'), schedule_terms=terms)


def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def apply_application_invoice(doc, method=None):
    if not doc.get('financed_invoice'):
        return
    basis = financial_snapshot(doc, require_invoice=True)
    doc.set('loan_amount', float(basis['principal']))
    doc.set('requested_advance_amount', float(basis['principal']))
    doc.set('financed_invoice_date', basis['invoice_date'])


def require_current_signed_packet(application, basis):
    """Historical packets stay available, but cannot authorize changed terms."""
    signature = frappe.db.get_value('Signature Request', {
        'reference_doctype': 'Loan Application', 'reference_name': application.name,
        'document_type': 'Flooring Packet', 'customer': application.applicant,
        'status': 'Signed', 'financial_basis_hash': snapshot_hash(basis),
    }, ['name', 'signed_attachment'], as_dict=True)
    if not signature or not signature.get('signed_attachment'):
        frappe.throw('The dealer must sign a Flooring Packet for the current final invoice before funding.')
    if not frappe.db.exists('File', {
        'file_url': signature['signed_attachment'], 'is_private': 1,
        'attached_to_doctype': 'Signature Request', 'attached_to_name': signature['name'],
    }):
        frappe.throw('The current signed Flooring Packet file is unavailable. Restore it before funding.')
    return signature


def validate_invoice_funding(doc, method=None):
    loan = frappe.get_doc('Loan', doc.against_loan)
    if not loan.get('home_build_request'):
        return
    if not loan.get('loan_application'):
        frappe.throw('A dealer Loan Application is required before funding this home.')
    application = frappe.get_doc('Loan Application', loan.loan_application)
    basis = financial_snapshot(application, require_invoice=True)
    if (doc.get('repayment_frequency') or loan.get('repayment_frequency') or 'Monthly') != 'Monthly':
        frappe.throw('DCR floorplan funding requires monthly repayments.')
    if (loan.applicant != application.applicant or loan.company != application.company or
            loan.home_build_request != application.home_build_request or
            loan.get('loan_product') != application.get('loan_product')):
        frappe.throw('Loan and application must belong to the same dealer, company, loan product and Home Build Request.')
    if (money(loan.loan_amount) != money(basis['principal']) or
            money(application.loan_amount) != money(basis['principal']) or
            (loan.get('qualifying_amount') and money(loan.qualifying_amount) != money(basis['principal']))):
        frappe.throw('Loan and application principal must match the final invoice plus additional financed fees. Revise the documents and packet before funding.')
    if interest_rate(loan.get('rate_of_interest')) != interest_rate(basis['annual_interest_rate']):
        frappe.throw('Loan interest rate must match the rate reviewed in the current Flooring Packet.')
    if not basis['first_payment_date'] or str(doc.get('repayment_start_date'))[:10] != basis['first_payment_date']:
        frappe.throw('First payment date must match the date reviewed in the current Flooring Packet.')
    if frappe.db.get_value('Company',loan.company,'interest_day_count_convention') != 'Actual/360':
        frappe.throw('Company interest day-count convention must be Actual/360 before funding.')
    if (basis['schedule_terms']['interest_only_periods'] != 12 or
            basis['schedule_terms']['monthly_principal_percent'] != 1):
        frappe.throw('DCR floorplan funding requires 12 interest-only payments followed by 1% of original principal.')
    require_current_signed_packet(application, basis)
    if str(doc.disbursement_date)[:10] != basis['invoice_date']:
        frappe.throw('Funding date must equal the Funding Invoice date ({0}).'.format(basis['invoice_date']))


def ensure_financing_fields():
    """Required metadata must migrate successfully before funding is enabled."""
    for field in [
        dict(fieldname='financed_invoice', label='Funding Invoice', fieldtype='Link',
             options='Purchase Invoice', insert_after='loan_amount',
             description='Submitted final purchase invoice, including freight and any fees already on it.'),
        dict(fieldname='financed_dcr_fees', label='DCR Fees Outside Invoice', fieldtype='Currency',
             insert_after='financed_invoice', non_negative=1, default='0',
             description='Only additional financed DCR fees not already included in the Funding Invoice.'),
        dict(fieldname='financed_invoice_date', label='Invoice / Funding Date', fieldtype='Date',
             insert_after='financed_dcr_fees', read_only=1),
        dict(fieldname='first_payment_date', label='First Payment Date', fieldtype='Date',
             insert_after='financed_invoice_date'),
    ]:
        if not frappe.get_meta('Loan Application').has_field(field['fieldname']):
            frappe.get_doc(dict(doctype='Custom Field', dt='Loan Application', depends_on='home_build_request', **field)).insert(ignore_permissions=True)
    # A native duplicate/amendment must receive a new signature. The original
    # packet remains on its original application and Signature Request.
    for field,property_name,property_type,value in (
        ('signed_packet','no_copy','Check','1'),
        ('status','no_copy','Check','1'),
        ('loan_amount','fetch_from','Small Text',''),
    ):
        filters = dict(doc_type='Loan Application',field_name=field,property=property_name)
        existing = frappe.db.exists('Property Setter',filters)
        if existing:
            if frappe.db.get_value('Property Setter',existing,'value') != value:
                frappe.db.set_value('Property Setter',existing,'value',value)
        else:
            frappe.get_doc(dict(doctype='Property Setter',doctype_or_field='DocField',
                                property_type=property_type,value=value,**filters)).insert(ignore_permissions=True)
    frappe.clear_cache(doctype='Loan Application')
