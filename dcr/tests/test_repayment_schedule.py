"""v16 schedules live in Loan Repayment Schedule, with Loan Demand balances."""
from types import SimpleNamespace as Row
from unittest.mock import patch
from datetime import date
import pytest
from dcr.tasks.scheduled_debits import get_next_unpaid_repayment


def schedule(name, day, amount, generated=0):
    return Row(name=name, payment_date=day, total_payment=amount, demand_generated=generated)


def run(rows, demands=(), schedules=('SCHED-1',)):
    with patch('dcr.tasks.scheduled_debits.frappe') as f:
        f.get_all.side_effect = [list(schedules), rows, list(demands)]
        result = get_next_unpaid_repayment(Row(name='LOAN-1'))
        return result, f.get_all.call_args_list


def test_reads_native_active_schedules_without_loan_child_table():
    result, calls = run([schedule('ROW-1','2025-03-01',1000)])
    assert result == (date(2025,3,1),1000)
    assert calls[0].args[0] == 'Loan Repayment Schedule'
    assert calls[0].kwargs['filters'] == {'loan':'LOAN-1','docstatus':1,'status':'Active'}
    assert calls[1].args[0] == 'Repayment Schedule'


def test_partial_payment_uses_unpaid_demand_amount():
    result, _ = run([schedule('ROW-1','2025-03-01',1000,1)], [Row(repayment_schedule_detail='ROW-1',outstanding_amount=250)])
    assert result == (date(2025,3,1),250)


def test_fully_paid_demand_skips_to_next_month():
    result, _ = run([schedule('ROW-1','2025-03-01',1000,1),schedule('ROW-2','2025-04-01',1000)], [Row(repayment_schedule_detail='ROW-1',outstanding_amount=0)])
    assert result == (date(2025,4,1),1000)


def test_sums_principal_and_interest_demands():
    result, _ = run([schedule('ROW-1','2025-03-01',1000,1)], [Row(repayment_schedule_detail='ROW-1',outstanding_amount=100),Row(repayment_schedule_detail='ROW-1',outstanding_amount=400)])
    assert result == (date(2025,3,1),500)


def test_missing_generated_demand_blocks_instead_of_inventing_balance():
    with pytest.raises(ValueError,match='no submitted demands'):
        run([schedule('ROW-1','2025-03-01',1000,1)])


def test_multiple_active_disbursement_schedules_sum_same_due_date():
    result, _ = run([schedule('ROW-1','2025-03-01',1000),schedule('ROW-2','2025-03-01',500)],schedules=['SCHED-1','SCHED-2'])
    assert result == (date(2025,3,1),1500)


def test_no_active_schedule_is_not_zero_payment():
    result, calls = run([], schedules=[])
    assert result == (None,None)
    assert len(calls) == 1


def test_no_future_rows_returns_no_payment():
    result, _ = run([])
    assert result == (None,None)
