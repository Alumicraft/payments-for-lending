"""Registered approval/cancel hooks restore the pre-approval financial state."""
import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest


class Doc(dict):
    __getattr__ = dict.get

    def db_set(self, field, value, **kwargs):
        self[field] = value


def run_hook(event, doc, frappe):
    tree = ast.parse((Path(__file__).parents[1] / 'hooks.py').read_text())
    events = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'doc_events' for t in n.targets))
    target = events['Loan Restructure'].get(event)
    if target:
        name, function = target.rsplit('.', 1)
        module = importlib.import_module(name)
        with patch.object(module, 'frappe', frappe):
            getattr(module, function)(doc, event)


@pytest.fixture
def trial():
    loan = Doc(name='LOAN-A', loan_product='Standard', original_financed_principal=225000, home_build_request='HBR-A',
        loan_amount=225000, rate_of_interest=12, monthly_repayment_amount=2325,
        total_payment=321000, total_interest_payable=96000, total_principal_paid=4500,
        total_amount_paid=36427.5, repayment_periods=112, tenure_post_restructure=0,
        days_past_due=0, loan_restructure_count=0, debit_adjustment_amount=0,
        credit_adjustment_amount=0, written_off_amount=0, status='Disbursed', is_npa=0)
    schedules = [Doc(name='RS-OLD', status='Active', loan_restructure=''),
                 Doc(name='RS-NEW', status='Initiated', loan_restructure='RES-A')]
    receipts = [Doc(name=name, loan_restructure='') for name in ('R8', 'R9', 'R10')]
    disbursements = [Doc(name='DISB-A')]
    f = MagicMock()
    f.get_doc.return_value = loan
    f.db.get_value.return_value = 'Interest Only Then Percent Principal'
    f.get_meta.return_value.has_field.return_value = True
    f.get_all.side_effect = lambda dt, **kwargs: {'Loan Repayment Schedule': schedules,
        'Loan Repayment': receipts, 'Loan Disbursement': disbursements}[dt]
    f.throw.side_effect = lambda message: (_ for _ in ()).throw(ValueError(message))
    def write(dt, name, values, *args, **kwargs):
        if dt == 'Loan': loan.update(values)
        else: next(s for s in schedules if s.name == name)['status'] = args[0]
    f.db.set_value.side_effect = write
    doc = Doc(name='RES-A', loan='LOAN-A', docstatus=1, status='Approved',
              restructure_type='Normal Restructure', is_npa=0)
    doc.flags = SimpleNamespace()
    doc.get_doc_before_save = lambda: Doc(status='Initiated')
    before = dict(loan)
    def approve():
        run_hook('before_update_after_submit', doc, f)
        assert not doc.get('dcr_restructure_snapshot'), 'capture must not change a submitted field before native validation'
        loan.update(loan_amount=220500, monthly_repayment_amount=6807, total_payment=300000,
                    total_interest_payable=79500, total_principal_paid=0, total_amount_paid=0,
                    repayment_periods=98, tenure_post_restructure=112, loan_restructure_count=1)
        schedules[0]['status'] = 'Restructured'; schedules[1]['status'] = 'Active'
        run_hook('on_update_after_submit', doc, f)
        persisted = Doc(doc)
        doc.get_doc_before_save = lambda: persisted
    def cancel():
        run_hook('before_cancel', doc, f)
        schedules.pop(); schedules[0]['status'] = 'Active'
        loan['loan_restructure_count'] = 0
        doc['docstatus'] = 2
        run_hook('on_cancel', doc, f)
    return SimpleNamespace(doc=doc, loan=loan, before=before, frappe=f, schedules=schedules,
                           receipts=receipts, disbursements=disbursements, approve=approve, cancel=cancel)


def test_native_cancel_restores_previous_totals_payment_and_paid_counters(trial):
    trial.approve()
    trial.cancel()
    assert dict(trial.loan) == trial.before
    assert trial.schedules[0]['status'] == 'Active'


@pytest.mark.parametrize('dependency', ['receipt', 'disbursement', 'schedule', 'loan_change'])
def test_later_financial_state_is_rejected_before_native_cancel(trial, dependency):
    trial.approve()
    if dependency == 'receipt': trial.receipts.append(Doc(name='NEW-RECEIPT', loan_restructure=''))
    elif dependency == 'disbursement': trial.disbursements.append(Doc(name='NEW-DISB'))
    elif dependency == 'schedule': trial.schedules.append(Doc(name='LATER-RS', status='Rejected', loan_restructure='LATER-RES'))
    else: trial.loan['credit_adjustment_amount'] = 10
    with pytest.raises(ValueError): run_hook('before_cancel', trial.doc, trial.frappe)
    assert trial.doc.docstatus == 1
    assert trial.schedules[1]['status'] == 'Active'


@pytest.mark.parametrize('corruption', ['', 'not json', '{}', '[]'])
def test_missing_or_invalid_legacy_snapshot_stops_cancellation(trial, corruption):
    trial.doc['dcr_restructure_snapshot'] = corruption
    trial.doc.get_doc_before_save = lambda: Doc(trial.doc)
    with pytest.raises(ValueError, match='snapshot'):
        run_hook('before_cancel', trial.doc, trial.frappe)
    trial.frappe.db.set_value.assert_not_called()


def test_npa_classification_changes_require_separate_review(trial):
    trial.doc['is_npa'] = 1
    trial.approve()
    with pytest.raises(ValueError, match='NPA'):
        run_hook('before_cancel', trial.doc, trial.frappe)


def test_cancelling_later_receipt_then_restructure_restores_state(trial):
    trial.approve()
    trial.receipts.append(Doc(name='LATER', loan_restructure=''))
    with pytest.raises(ValueError): run_hook('before_cancel', trial.doc, trial.frappe)
    trial.receipts.pop()
    trial.cancel()
    assert dict(trial.loan) == trial.before


def test_native_restructure_adjustment_receipts_are_left_to_native_reversal(trial):
    trial.approve()
    trial.receipts.append(Doc(name='OWN-ADJUSTMENT', loan_restructure=trial.doc.name))
    run_hook('before_cancel', trial.doc, trial.frappe)


def test_unrelated_submitted_edits_do_not_recapture_approved_state(trial):
    trial.approve()
    snapshot = trial.doc.dcr_restructure_snapshot
    trial.loan['monthly_repayment_amount'] = 9000
    run_hook('on_update_after_submit', trial.doc, trial.frappe)
    assert trial.doc.dcr_restructure_snapshot == snapshot
    with pytest.raises(ValueError): run_hook('before_cancel', trial.doc, trial.frappe)


@pytest.mark.parametrize('change', [('restructure_type', 'Pre Payment'), ('product', 'Amortizing')])
def test_other_native_workflows_do_not_capture_or_restore(trial, change):
    if change[0] == 'product': trial.frappe.db.get_value.return_value = change[1]
    else: trial.doc[change[0]] = change[1]
    trial.approve()
    assert not trial.doc.get('dcr_restructure_snapshot')
    run_hook('before_cancel', trial.doc, trial.frappe)
    trial.frappe.db.set_value.assert_not_called()


def test_required_snapshot_field_is_created_once_hidden_and_not_copyable():
    from dcr.api import financing_basis
    with patch.object(financing_basis, 'frappe') as f:
        exists = False
        def meta(dt):
            return SimpleNamespace(has_field=lambda field: exists if dt == 'Loan Restructure' else True)
        f.get_meta.side_effect = meta
        f.db.exists.return_value = True
        def insert(**kwargs):
            nonlocal exists
            exists = True
        field = MagicMock()
        field.insert.side_effect = insert
        f.get_doc.return_value = field
        financing_basis.ensure_financing_fields()
        financing_basis.ensure_financing_fields()
        records = [c.args[0] for c in f.get_doc.call_args_list]
        assert len(records) == 1
        assert records[0]['dt'] == 'Loan Restructure'
        assert records[0]['fieldtype'] == 'Long Text'
        assert records[0]['hidden'] == records[0]['read_only'] == records[0]['no_copy'] == 1
        assert not records[0].get('allow_on_submit')


def test_two_successive_restructures_can_be_cancelled_in_reverse_order(trial):
    trial.approve()
    first_state = dict(trial.loan)
    second = Doc(name='RES-B', loan='LOAN-A', docstatus=1, status='Approved',
                 restructure_type='Normal Restructure', is_npa=0)
    second.flags = SimpleNamespace()
    second.get_doc_before_save = lambda: Doc(status='Initiated')
    trial.schedules.append(Doc(name='RS-B', status='Initiated', loan_restructure='RES-B'))
    run_hook('before_update_after_submit', second, trial.frappe)
    trial.loan.update(monthly_repayment_amount=7000, rate_of_interest=13, loan_restructure_count=2)
    trial.schedules[1]['status'] = 'Restructured'; trial.schedules[2]['status'] = 'Active'
    run_hook('on_update_after_submit', second, trial.frappe)
    saved_second = Doc(second)
    second.get_doc_before_save = lambda: saved_second
    with pytest.raises(ValueError): run_hook('before_cancel', trial.doc, trial.frappe)
    run_hook('before_cancel', second, trial.frappe)
    trial.schedules.pop(); trial.schedules[1]['status'] = 'Active'
    trial.loan['loan_restructure_count'] = 1
    second['docstatus'] = 2
    run_hook('on_cancel', second, trial.frappe)
    assert dict(trial.loan) == first_state
    trial.cancel()
    assert dict(trial.loan) == trial.before


@pytest.mark.parametrize('field,value', [('loan', 'OTHER-LOAN'), ('status', 'Initiated'),
    ('restructure_type', 'Pre Payment'), ('dcr_restructure_snapshot', '')])
def test_cancel_payload_cannot_bypass_the_saved_approval_boundary(trial, field, value):
    trial.approve()
    trial.doc[field] = value
    with pytest.raises(ValueError, match='Reload'):
        run_hook('before_cancel', trial.doc, trial.frappe)
    trial.frappe.db.set_value.assert_not_called()


def test_post_cancel_restore_requires_the_validated_before_cancel_context(trial):
    trial.approve()
    run_hook('on_cancel', trial.doc, trial.frappe)
    trial.frappe.db.set_value.assert_not_called()
