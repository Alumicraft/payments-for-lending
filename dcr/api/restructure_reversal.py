"""Restore approved floorplan terms only from a recorded approval boundary."""
import json

import frappe


SNAPSHOT_FIELD = 'dcr_restructure_snapshot'
LOAN_FIELDS = ('loan_amount', 'rate_of_interest', 'monthly_repayment_amount',
    'total_payment', 'total_interest_payable', 'total_principal_paid',
    'total_amount_paid', 'repayment_periods', 'tenure_post_restructure',
    'days_past_due', 'loan_restructure_count')
GUARD_FIELDS = LOAN_FIELDS + ('debit_adjustment_amount', 'credit_adjustment_amount',
    'written_off_amount', 'status', 'is_npa', 'loan_product', 'original_financed_principal')


def _loan(doc):
    return frappe.get_doc('Loan', doc.loan, for_update=True)


def _applies(doc, loan):
    return (doc.restructure_type == 'Normal Restructure' and (doc.get(SNAPSHOT_FIELD) or
        frappe.db.get_value('Loan Product', doc.get('loan_product') or loan.loan_product,
                            'custom_schedule_type') == 'Interest Only Then Percent Principal'))


def _state(loan, fields):
    return json.loads(json.dumps({field: loan.get(field) for field in fields}, default=str))


def _schedules(loan):
    return frappe.get_all('Loan Repayment Schedule', filters={'loan': loan, 'docstatus': 1},
                          fields=['name', 'status', 'loan_restructure'], limit_page_length=0)


def _schedule_states(loan):
    return {row.name: row.status for row in _schedules(loan)}


def _receipts(doc):
    rows = frappe.get_all('Loan Repayment', filters={'against_loan': doc.loan, 'docstatus': 1},
                         fields=['name', 'loan_restructure'], limit_page_length=0)
    return sorted(row.name for row in rows if row.loan_restructure != doc.name)


def _funding(doc):
    return sorted(row.name for row in frappe.get_all('Loan Disbursement',
        filters={'against_loan': doc.loan, 'docstatus': 1}, fields=['name'], limit_page_length=0))


def capture_before_approval(doc, method=None):
    previous = doc.get_doc_before_save()
    if (doc.status != 'Approved' or doc.restructure_type != 'Normal Restructure'
            or not previous or previous.status != 'Initiated'):
        return
    loan = _loan(doc)
    if not _applies(doc, loan):
        return
    if not frappe.get_meta('Loan Restructure').has_field(SNAPSHOT_FIELD):
        frappe.throw('Migrate the DCR restructure snapshot field before approval.')
    if doc.get(SNAPSHOT_FIELD):
        frappe.throw('This restructure already has an approval snapshot. Review its history before approving again.')
    schedules = _schedules(doc.loan)
    if not any(row.loan_restructure == doc.name for row in schedules):
        frappe.throw('The submitted restructure schedule is missing. Approval was stopped.')
    doc.flags.dcr_restructure_before = {
        'version': 1, 'loan': doc.loan, 'restructure': doc.name,
        'prior_values': _state(loan, LOAN_FIELDS),
        'prior_schedules': {row.name: row.status for row in schedules if row.loan_restructure != doc.name},
        'receipts': _receipts(doc), 'funding': _funding(doc),
        'requires_npa_review': bool(doc.get('is_npa') or loan.get('is_npa')),
    }


def capture_after_approval(doc, method=None):
    snapshot = getattr(doc.flags, 'dcr_restructure_before', None)
    if not snapshot:
        return
    snapshot['approved_values'] = _state(_loan(doc), GUARD_FIELDS)
    snapshot['approved_schedules'] = _schedule_states(doc.loan)
    doc.db_set(SNAPSHOT_FIELD, json.dumps(snapshot, sort_keys=True), update_modified=False)
    doc.flags.dcr_restructure_before = None


def _snapshot(doc):
    try:
        snapshot = json.loads(doc.get(SNAPSHOT_FIELD) or '')
        valid = (snapshot['version'] == 1 and snapshot['loan'] == doc.loan
            and snapshot['restructure'] == doc.name
            and isinstance(snapshot['prior_values'], dict)
            and isinstance(snapshot['approved_values'], dict)
            and set(snapshot['prior_values']) == set(LOAN_FIELDS)
            and set(snapshot['approved_values']) == set(GUARD_FIELDS)
            and isinstance(snapshot['prior_schedules'], dict)
            and isinstance(snapshot['approved_schedules'], dict)
            and set(snapshot['prior_schedules']).issubset(snapshot['approved_schedules'])
            and isinstance(snapshot['requires_npa_review'], bool)
            and isinstance(snapshot['receipts'], list) and isinstance(snapshot['funding'], list))
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        frappe.throw('This restructure has no valid pre-approval snapshot. Accounting review is required before cancellation.')
    return snapshot


def guard_cancellation(doc, method=None):
    persisted = doc.get_doc_before_save()
    if not persisted or persisted.status != 'Approved' or persisted.restructure_type != 'Normal Restructure':
        return
    loan = _loan(persisted)
    if not _applies(persisted, loan):
        return
    if any(doc.get(field) != persisted.get(field) for field in (
        'loan', 'status', 'restructure_type', SNAPSHOT_FIELD
    )):
        frappe.throw('Reload the approved restructure before cancelling. Its loan, status and snapshot must match the saved record.')
    snapshot = _snapshot(persisted)
    if snapshot.get('requires_npa_review'):
        frappe.throw('Cancellation of an NPA restructure requires review of the linked dealer and loan classifications.')
    if (_state(loan, GUARD_FIELDS) != snapshot['approved_values']
            or _schedule_states(doc.loan) != snapshot['approved_schedules']
            or _receipts(doc) != snapshot['receipts'] or _funding(doc) != snapshot['funding']):
        frappe.throw('The loan has financial changes after this approval. Reverse later receipts, funding or restructures and review adjustments before cancelling.')
    doc.flags.dcr_restructure_cancel_snapshot = snapshot


def restore_after_cancellation(doc, method=None):
    snapshot = getattr(doc.flags, 'dcr_restructure_cancel_snapshot', None)
    if not snapshot:
        return
    frappe.db.set_value('Loan', doc.loan, snapshot['prior_values'])
    for name, status in snapshot['prior_schedules'].items():
        frappe.db.set_value('Loan Repayment Schedule', name, 'status', status)
    doc.flags.dcr_restructure_cancel_snapshot = None
