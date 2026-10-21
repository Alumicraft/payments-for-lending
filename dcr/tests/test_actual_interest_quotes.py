"""Future quote consumers must use paid principal, not scheduled reductions."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from dcr.api import floorplan_accrual as accrual


class Record(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


@pytest.fixture
def quote_environment():
    original = Mock(return_value=171000)
    native = SimpleNamespace(get_principal_amount_for_term_loan=original)
    loan = Record(name='LOAN', rate_of_interest=12)
    def quote():
        return round(native.get_principal_amount_for_term_loan('SCHEDULE', '2029-11-01') * .12 / 360, 2)
    def records(doctype, **kwargs):
        assert kwargs['filters']['docstatus'] == 1
        if doctype == 'Loan Disbursement':
            return [Record(disbursement_date='2026-10-01', disbursed_amount=225000)]
        assert doctype == 'Loan Repayment'
        return [Record(value_date=day, principal_amount_paid=2250) for day in
                ('2027-11-01', '2027-12-01', '2028-02-01')]
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_interest_accrual':
            SimpleNamespace(loan_interest_accrual=native),
    }), patch.object(accrual, 'frappe') as frappe, \
            patch.object(accrual, 'floorplan_loan', return_value=loan) as eligibility:
        frappe.db.get_value.return_value = 'LOAN'
        frappe.get_all.side_effect = records
        yield native, original, quote, eligibility


@pytest.mark.parametrize('kind', ['Advance Payment', 'Pre Payment'])
@pytest.mark.parametrize('details', [False, True])
def test_repayment_api_quote_uses_actual_unpaid_principal(quote_environment, kind, details):
    native, original, quote, _ = quote_environment
    amounts = {'unaccrued_interest':57, 'interest_amount':46487.25, 'marker':'native'}
    def calculate(*args, **kwargs):
        amounts['unaccrued_interest'] = quote()
        return {'amounts':amounts, 'loan_details':{'native':True}} if details else amounts
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':
            SimpleNamespace(calculate_amounts=calculate),
    }):
        result = accrual.calculate_amounts('LOAN', '2029-11-02', payment_type=kind,
                                          with_loan_details=details)
    assert (result['amounts'] if details else result) == {
        'unaccrued_interest':72.75, 'interest_amount':46487.25, 'marker':'native'}
    assert native.get_principal_amount_for_term_loan is original


@pytest.mark.parametrize('kind', ['Advance Payment', 'Pre Payment'])
def test_denied_quote_restores_native_function_without_reading_financial_events(quote_environment, kind):
    native, original, _, eligibility = quote_environment
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':
            SimpleNamespace(calculate_amounts=Mock(side_effect=PermissionError('denied'))),
    }):
        with pytest.raises(PermissionError, match='denied'):
            accrual.calculate_amounts('LOAN', '2029-11-02', payment_type=kind)
    eligibility.assert_not_called()
    assert native.get_principal_amount_for_term_loan is original


@pytest.mark.parametrize('phase', ['validate', 'on_submit'])
@pytest.mark.parametrize('kind', ['Advance Payment', 'Pre Payment'])
def test_repayment_controller_uses_actual_principal_in_native_calculation(quote_environment, phase, kind):
    native, original, quote, _ = quote_environment
    class Native(Record):
        def validate(self):
            self.projected_interest = quote()
        def on_submit(self):
            self.projected_interest = quote()
    name = 'dcr.overrides.loan_repayment'
    previous = sys.modules.pop(name, None)
    try:
        with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_repayment.loan_repayment':
                SimpleNamespace(LoanRepayment=Native),
        }):
            module = importlib.import_module(name)
            doc = module.CustomLoanRepayment(repayment_type=kind, against_loan='LOAN')
            with patch.object(doc, '_reopen_legacy_interest_only_loan'):
                getattr(doc, phase)()
            assert doc.projected_interest == 72.75
            assert native.get_principal_amount_for_term_loan is original
    finally:
        sys.modules.pop(name, None)
        if previous is not None:
            sys.modules[name] = previous


@pytest.mark.parametrize('eligible', [True, False])
def test_registered_restructure_controller_preserves_native_fields_and_legacy_quotes(quote_environment, eligible):
    native, original, quote, eligibility = quote_environment
    if not eligible:
        eligibility.return_value = None
    class Native(Record):
        def update_overdue_amounts(self):
            self.unaccrued_interest = quote()
            self.interest_overdue = 46487.25
            return 'native-result'
    from dcr import hooks
    path = hooks.override_doctype_class['Loan Restructure']
    module_name, class_name = path.rsplit('.', 1)
    previous = sys.modules.pop(module_name, None)
    try:
        with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_restructure.loan_restructure':
                SimpleNamespace(LoanRestructure=Native),
        }):
            controller = getattr(importlib.import_module(module_name), class_name)
            doc = controller(loan='LOAN')
            assert doc.update_overdue_amounts() == 'native-result'
            assert doc.unaccrued_interest == (72.75 if eligible else 57)
            assert doc.interest_overdue == 46487.25
            assert native.get_principal_amount_for_term_loan is original
    finally:
        sys.modules.pop(module_name, None)
        if previous is not None:
            sys.modules[module_name] = previous
