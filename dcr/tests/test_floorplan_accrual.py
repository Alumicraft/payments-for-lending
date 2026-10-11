from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
import importlib
import sys

import pytest

from dcr.api import floorplan_accrual as accrual


class Doc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


def loan(**changes):
    fields = dict(name='LOAN', loan_product='Standard', company='DCR',
                  original_financed_principal=225000, home_build_request='HOME', rate_of_interest=12)
    fields.update(changes)
    return Doc(**fields)


def get_all(doctype, filters, fields, **kwargs):
    assert filters['docstatus'] == 1
    if doctype == 'Loan Disbursement':
        return [Doc(disbursement_date='2026-10-01', disbursed_amount=225000)]
    if doctype == 'Loan Repayment':
        return [Doc(value_date='2027-11-01', principal_amount_paid=2250),
                Doc(value_date='2027-12-01', principal_amount_paid=2250)]
    assert doctype == 'Loan Interest Accrual'
    assert filters['posting_date'] == ['<', '2028-01-15']
    return [Doc(posting_date='2027-11-30')]


def test_projected_payoff_matches_actual_balance_and_elapsed_days():
    with patch.object(accrual, 'frappe') as frappe:
        frappe.db.get_value.return_value = 'Daily'
        frappe.get_all.side_effect = get_all
        assert accrual.projected_interest(loan(), '2028-01-15') == Decimal('3307.50')


@pytest.mark.parametrize('with_details,for_update,old', [(False,False,3369.75),
                                                       (True,False,3369.75), (False,True,0)])
def test_quote_and_locked_validation_keep_native_fields_and_fix_projection(with_details, for_update, old):
    amounts = dict(unaccrued_interest=old, interest_amount=old, payable_amount=220500+old,
                   pending_principal_amount=220500, total_charges_payable=0, marker='native')
    native_result = {'amounts': amounts, 'loan_details': {'native':True}} if with_details else amounts
    native = Mock(return_value=native_result)
    module = SimpleNamespace(calculate_amounts=native)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_repayment.loan_repayment':module}), \
            patch.object(accrual, 'floorplan_loan', return_value=loan()), \
            patch.object(accrual, 'frappe') as frappe:
        frappe.db.get_value.return_value = 'Daily'
        frappe.get_all.side_effect = get_all
        result = accrual.calculate_amounts('LOAN','2028-01-15', payment_type='Loan Closure',
                                         with_loan_details=with_details,for_update=for_update)
    assert result is native_result
    assert amounts['interest_amount'] == 3307.50
    assert amounts['payable_amount'] == 223807.50
    assert amounts['pending_principal_amount'] == 220500
    assert amounts['marker'] == 'native'
    native.assert_called_once()
    assert native.call_args.kwargs['for_update'] is for_update


def test_permission_failure_precedes_any_dcr_financial_reads():
    module = SimpleNamespace(calculate_amounts=Mock(side_effect=PermissionError('denied')))
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_repayment.loan_repayment':module}), \
            patch.object(accrual, 'floorplan_loan') as eligibility:
        with pytest.raises(PermissionError):
            accrual.calculate_amounts('LOAN','2028-01-15',payment_type='Loan Closure')
        eligibility.assert_not_called()


def test_normal_payment_keeps_native_calculation():
    result = {'payable_amount':4575}
    module = SimpleNamespace(calculate_amounts=Mock(return_value=result))
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_repayment.loan_repayment':module}), \
            patch.object(accrual, 'adjust_closure_amounts') as adjust:
        assert accrual.calculate_amounts('LOAN','2027-11-01',payment_type='Normal Repayment') is result
        adjust.assert_not_called()


@pytest.mark.parametrize('changes', [{'original_financed_principal':0}, {'home_build_request':None}])
def test_legacy_and_unrelated_loans_are_preserved(changes):
    with patch.object(accrual, 'frappe') as frappe, patch.object(accrual,'product_terms') as terms:
        frappe.get_doc.return_value = loan(**changes)
        assert accrual.floorplan_loan('LOAN') is None
        terms.assert_not_called()


def test_adjusted_principal_requires_review_instead_of_forecast_guess():
    with patch.object(accrual,'frappe') as frappe:
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            accrual.principal_events(loan(debit_adjustment_amount=100))
        frappe.get_all.assert_not_called()


def test_accrual_uses_receipts_and_restores_native_function_on_failure():
    original = Mock(return_value=999)
    native = SimpleNamespace(get_principal_amount_for_term_loan=original)
    package = SimpleNamespace(loan_interest_accrual=native)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_interest_accrual':package}), \
            patch.object(accrual,'frappe') as frappe, \
            patch.object(accrual,'floorplan_loan', return_value=loan()):
        frappe.db.get_value.return_value = 'LOAN'
        frappe.get_all.side_effect = get_all
        with pytest.raises(RuntimeError):
            with accrual.actual_principal_accruals():
                assert native.get_principal_amount_for_term_loan('SCHEDULE','2027-11-01') == 222750
                assert native.get_principal_amount_for_term_loan('SCHEDULE','2028-01-01') == 220500
                raise RuntimeError('posting failed')
        assert native.get_principal_amount_for_term_loan is original
        assert frappe.get_all.call_count == 2


def test_native_accrual_stays_native_for_legacy_schedule():
    original = Mock(return_value=1000)
    native = SimpleNamespace(get_principal_amount_for_term_loan=original)
    package = SimpleNamespace(loan_interest_accrual=native)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_interest_accrual':package}), \
            patch.object(accrual,'frappe') as frappe, \
            patch.object(accrual,'floorplan_loan',return_value=None):
        frappe.db.get_value.return_value = 'LEGACY'
        with accrual.actual_principal_accruals():
            assert native.get_principal_amount_for_term_loan('SCHEDULE','2028-01-01') == 1000
        original.assert_called_once_with('SCHEDULE','2028-01-01')


def test_submit_books_interest_before_final_allocation():
    events = []
    class Native:
        def before_submit(self):
            events.append('native before submit')
    native_module = SimpleNamespace(LoanRepayment=Native)
    process = Mock(side_effect=lambda **kwargs: events.append(('accrual',kwargs)))
    process_module = SimpleNamespace(process_loan_interest_accrual_for_loans=process)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':native_module,
        'lending.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual':process_module,
    }), patch.object(accrual,'floorplan_loan',return_value=loan()):
        previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
        controller = importlib.import_module('dcr.overrides.loan_repayment')
        doc = controller.CustomLoanRepayment()
        doc.repayment_type='Loan Closure';doc.against_loan='LOAN';doc.value_date='2028-01-15';doc.loan_disbursement=None
        doc.validate=lambda:events.append('validate')
        try:
            doc.before_submit()
        finally:
            sys.modules.pop('dcr.overrides.loan_repayment', None)
            if previous is not None:
                sys.modules['dcr.overrides.loan_repayment'] = previous
    assert events[0][0] == 'accrual'
    assert events[0][1]['posting_date'] == date(2028,1,14)
    assert events[0][1]['loan'] == 'LOAN'
    assert events[1:] == ['validate','native before submit']


def test_locked_draft_allocation_gets_projection_without_posting_accrual():
    class Native:
        def set_missing_values(self, amounts):
            self.interest_payable = amounts['interest_amount']
            return amounts
    module = SimpleNamespace(LoanRepayment=Native)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_repayment.loan_repayment': module}), \
            patch.object(accrual, 'floorplan_loan', return_value=loan()), \
            patch.object(accrual, 'projected_interest', return_value=Decimal('3307.50')):
        previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
        controller = importlib.import_module('dcr.overrides.loan_repayment')
        try:
            doc = controller.CustomLoanRepayment()
            doc.repayment_type = 'Loan Closure'
            doc.against_loan = 'LOAN'
            doc.value_date = '2028-01-15'
            amounts = dict(interest_amount=0, unaccrued_interest=0, payable_amount=220500)
            assert doc.set_missing_values(amounts) is amounts
            assert doc.interest_payable == 3307.50
            assert amounts['payable_amount'] == 223807.50
        finally:
            sys.modules.pop('dcr.overrides.loan_repayment', None)
            if previous is not None:
                sys.modules['dcr.overrides.loan_repayment'] = previous


def test_posted_accrual_is_not_projected_again():
    with patch.object(accrual, 'floorplan_loan', return_value=loan()), \
            patch.object(accrual, 'projected_interest', return_value=Decimal(0)):
        amounts = dict(interest_amount=3307.50, unaccrued_interest=0, payable_amount=223807.50)
        accrual.adjust_closure_amounts('LOAN', '2028-01-15', amounts)
        assert amounts == dict(interest_amount=3307.50, unaccrued_interest=0, payable_amount=223807.50)
