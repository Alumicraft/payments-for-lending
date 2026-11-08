from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys

import pytest

from dcr.tests.test_loan_repayment_schedule_override import import_override_with_stubs


@pytest.mark.parametrize('paid_interest', [0, 100])
def test_extra_principal_does_not_invent_interest_collection_or_skip_the_next_installment(paid_interest):
    module, frappe = import_override_with_stubs()
    frappe.db.get_value.return_value = SimpleNamespace(adjusted_unaccrued_interest=paid_interest,
        balance_principal=-5000, loan_repayment='RECEIPT')
    demand, accrue = Mock(), Mock()
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_demand.loan_demand':
            SimpleNamespace(create_loan_demand=demand),
        'lending.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual':
            SimpleNamespace(process_loan_interest_accrual_for_loans=accrue),
    }):
        schedule = module.CustomLoanRepaymentSchedule()
        schedule.name='SCHEDULE'; schedule.loan='LOAN'; schedule.loan_restructure='RESTRUCTURE'
        schedule.loan_disbursement=None; schedule.posting_date='2028-01-15'
        schedule.restructure_type='Pre Payment'
        schedule.is_dcr_floorplan_structure=lambda:True
        with patch('frappe.utils.add_days', return_value=date(2028,1,14)):
            schedule.make_demand_for_advance_payment()
    accrue.assert_called_once_with(posting_date=date(2028,1,14),loan='LOAN',
                                   loan_disbursement=None,from_demand=True)
    assert [(c.args[3],c.args[4]) for c in demand.call_args_list] == (
        [('Interest',100),('Principal',5000)] if paid_interest else [('Principal',5000)])
    for call in demand.call_args_list:
        assert call.kwargs['paid_amount'] == call.args[4]
        assert call.kwargs['loan_repayment'] == 'RECEIPT'
        assert 'repayment_schedule_detail' not in call.kwargs
