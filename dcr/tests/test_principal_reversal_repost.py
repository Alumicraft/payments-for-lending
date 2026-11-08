"""Cancelling principal must rebuild interest even without a later receipt."""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


class Record(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


@pytest.mark.parametrize('future', ['Loan Interest Accrual', 'Loan Demand', None])
@pytest.mark.parametrize('case', ['cancel', 'submit', 'imported', 'other_product',
                                'no_principal', 'native_repost', 'write_off'])
def test_principal_cancellation_enters_native_repost_when_interest_depends_on_it(future, case):
    class Native(Record):
        def check_future_entries(self, cancel=0):
            self.is_backdated = case == 'native_repost'
            return 'native'

    name = 'dcr.overrides.loan_repayment'
    previous = sys.modules.pop(name, None)
    try:
        with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_repayment.loan_repayment':
                SimpleNamespace(LoanRepayment=Native),
        }):
            module = importlib.import_module(name)
            with patch('dcr.api.floorplan_accrual.floorplan_loan',
                       return_value=None if case == 'other_product' else object()), \
                    patch.object(module, 'frappe') as f:
                def exists(kind, filters):
                    assert filters['loan'] == 'LOAN'
                    assert filters['docstatus'] == 1
                    assert filters['loan_disbursement'] == 'DISB'
                    assert filters['posting_date' if kind == 'Loan Interest Accrual' else 'demand_date'] == ['>=', '2028-01-15']
                    if kind == 'Loan Interest Accrual':
                        assert filters['interest_type'] == 'Normal Interest'
                    else:
                        assert filters['demand_type'] == 'EMI'
                    return kind == future
                f.db.exists.side_effect = exists
                doc = module.CustomLoanRepayment(against_loan='LOAN', loan_disbursement='DISB',
                    value_date='2028-01-15', principal_amount_paid=0 if case == 'no_principal' else 5000,
                    is_imported=case == 'imported', is_write_off_waiver=case == 'write_off',
                    db_set=Mock())
                assert doc.check_future_entries(cancel=0 if case == 'submit' else 1) == 'native'
                rebuild = case == 'cancel' and future is not None
                assert doc.is_backdated == (rebuild or case == 'native_repost')
                if rebuild:
                    doc.db_set.assert_called_once_with('is_backdated', True)
                else:
                    doc.db_set.assert_not_called()
    finally:
        sys.modules.pop(name, None)
        if previous is not None:
            sys.modules[name] = previous
