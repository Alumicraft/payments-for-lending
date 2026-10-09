"""Owner-approved invoice-basis, dated interest and continuing-payment cases."""
from datetime import date
from types import SimpleNamespace
import pytest


def rows(**changes):
    from dcr.lending_rules import floorplan_schedule
    values = dict(original_principal=225000, outstanding_principal=225000, annual_rate=12,
                  interest_start_date='2026-01-01', first_payment_date='2026-02-01')
    values.update(changes)
    return floorplan_schedule(**values)


def test_fixed_original_financed_amount_at_payments_12_13_14():
    result = rows()
    assert result[11]['principal_amount'] == 0
    assert result[12]['principal_amount'] == result[13]['principal_amount'] == 2250
    assert result[12]['balance_loan_amount'] == 222750
    assert result[13]['balance_loan_amount'] == 220500
    assert result[13]['interest_amount'] == 2079, '28 actual February days, not a fixed month'


def test_continues_past_36_without_balloon_until_principal_reaches_zero():
    result = rows()
    assert len(result) == 112
    assert result[35]['balance_loan_amount'] == 171000
    assert result[36]['principal_amount'] == 2250
    assert result[-1]['balance_loan_amount'] == 0
    assert sum(row['principal_amount'] for row in result) == 225000


@pytest.mark.parametrize('start,due,days,interest', [
    ('2027-02-01','2027-03-01',28,2053.33),
    ('2028-02-01','2028-03-01',29,2126.67),
    ('2026-01-20','2026-02-01',12,880),
])
def test_actual360_counts_start_through_day_before_due(start,due,days,interest):
    first = rows(original_principal=220000,outstanding_principal=220000,
                 interest_start_date=start,first_payment_date=due)[0]
    assert first['number_of_days'] == days
    assert first['interest_amount'] == interest


def test_rebuild_retains_original_basis_and_does_not_restart_interest_only():
    result = rows(outstanding_principal=5000, prior_periods=13,
                  interest_start_date='2027-02-01',first_payment_date='2027-03-01')
    assert [row['principal_amount'] for row in result] == [2250,2250,500]
    assert result[-1]['balance_loan_amount'] == 0


def test_month_end_payments_keep_calendar_anchor_after_february():
    result = rows(interest_start_date='2026-01-31',first_payment_date='2026-02-28')
    assert [row['payment_date'] for row in result[:3]] == [date(2026,2,28),date(2026,3,31),date(2026,4,30)]


@pytest.mark.parametrize('changes', [dict(first_payment_date='2025-12-31'),
                                    dict(original_principal=0),dict(monthly_principal_percent=0)])
def test_invalid_financial_inputs_fail_explicitly(changes):
    with pytest.raises(ValueError):
        rows(**changes)


def test_installed_v16_call_preserves_prior_rows_and_uses_passed_balance():
    from dcr.tests.test_loan_repayment_schedule_override import import_override_with_stubs
    module, frappe = import_override_with_stubs()
    schedule = module.CustomLoanRepaymentSchedule()
    prior = [SimpleNamespace(payment_date=date(2026,month,1),principal_amount=0,
                             interest_amount=2250,total_payment=2250,balance_loan_amount=225000)
             for month in range(1,13)]
    saved = {'repayment_schedule':prior.copy()}
    schedule.get = lambda key: saved.get(key)
    schedule.set = lambda key,value: saved.update({key:value})
    schedule.append = lambda key,value: saved[key].append(SimpleNamespace(**value))
    schedule.is_dcr_floorplan_structure = lambda: True
    schedule.loan_product = 'Standard'
    schedule.loan = 'LOAN-1'
    schedule.loan_amount = 225000
    schedule.current_principal_amount = 225000  # native argument must win
    schedule.repayment_start_date = '2027-01-01'
    schedule.posting_date = '2026-12-01'
    schedule.repayment_periods = 36
    schedule.rate_of_interest = 12
    schedule.get_loan_product_value = lambda *names: 12 if 'custom_interest_only_months' in names else 1
    schedule.get_contract_interest_rate = lambda: 12
    frappe.db.get_value.return_value = 225000
    schedule.make_repayment_schedule('repayment_schedule',0,5000,0,0,12,100,100)
    assert saved['repayment_schedule'][:12] == prior
    new = saved['repayment_schedule'][12:]
    assert [row.principal_amount for row in new] == [2250,2250,500]
    assert new[-1].balance_loan_amount == 0
    assert schedule.number_of_rows == 3


def test_carried_interest_is_applied_once_not_every_future_month():
    result = rows(carried_interest=100)
    assert result[0]['interest_amount'] == 2425
    assert result[1]['interest_amount'] == 2100


def test_successive_restructures_keep_original_invoice_principal_basis():
    from dcr.tests.test_loan_repayment_schedule_override import import_override_with_stubs
    module, frappe = import_override_with_stubs()
    schedule = module.CustomLoanRepaymentSchedule()
    schedule.loan = 'LOAN-1'
    schedule.rate_of_interest = 12
    schedule.get_contract_interest_rate = lambda: 12
    schedule.get_loan_product_value = lambda *names: 12 if 'custom_interest_only_months' in names else 1
    schedule._dcr_prior_periods = 14
    schedule.posting_date = '2027-03-01'
    schedule.repayment_start_date = '2027-04-01'
    saved = {'repayment_schedule': []}
    schedule.get = lambda key: saved.get(key)
    schedule.append = lambda key, value: saved[key].append(SimpleNamespace(**value))
    for remaining in (220500, 218250):
        # Native Loan Restructure.update_totals writes the new balance to
        # Loan.loan_amount. The original invoice basis must remain 225,000.
        schedule.loan_amount = remaining
        frappe.db.get_value.side_effect = lambda dt, name, field: 225000 if field == 'original_financed_principal' else remaining
        saved['repayment_schedule'] = []
        schedule.make_dcr_repayment_schedule('repayment_schedule', balance_amount=remaining)
        assert saved['repayment_schedule'][0].principal_amount == 2250
        assert schedule.get_floorplan_principal_reduction(14, remaining) == 2250


def test_zero_outstanding_principal_has_no_future_charges():
    assert rows(outstanding_principal=0) == []


def test_one_time_payoff_uses_all_remaining_principal_and_no_future_interest():
    from dcr.tests.test_loan_repayment_schedule_override import import_override_with_stubs
    module, frappe = import_override_with_stubs()
    schedule = module.CustomLoanRepaymentSchedule()
    saved = {'repayment_schedule':[]}
    schedule.get = lambda key: saved.get(key)
    schedule.append = lambda key,value: saved[key].append(SimpleNamespace(**value))
    schedule.loan = 'LOAN-1'; schedule.loan_amount = 225000
    schedule.current_principal_amount = 5000
    schedule.repayment_frequency = 'One Time'
    schedule.repayment_start_date = '2027-02-11'; schedule.posting_date = '2027-02-01'
    schedule.rate_of_interest = 12
    schedule.get_contract_interest_rate = lambda: 12
    schedule.get_loan_product_value = lambda *names: 12 if 'custom_interest_only_months' in names else 1
    frappe.db.get_value.return_value = 225000
    schedule.make_dcr_repayment_schedule('repayment_schedule',balance_amount=5000)
    assert len(saved['repayment_schedule']) == 1
    row = saved['repayment_schedule'][0]
    assert row.principal_amount == 5000
    assert row.interest_amount == 16.67
    assert row.total_payment == 5016.67
    assert row.balance_loan_amount == 0
