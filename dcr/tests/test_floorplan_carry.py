"""Exercise carry through the real DCR controller before its future-row builder."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from dcr.tests.test_loan_repayment_schedule_override import import_override_with_stubs


def fixture(*, old_due='2026-01-01', due='2026-02-01', posting='2026-01-16'):
    module, frappe = import_override_with_stubs()
    schedule = module.CustomLoanRepaymentSchedule()
    row = SimpleNamespace(payment_date=date.fromisoformat(old_due), principal_amount=0,
                          interest_amount=800, total_payment=800, balance_loan_amount=80000,
                          number_of_days=30, demand_generated=1)
    previous = SimpleNamespace(posting_date=date(2025,12,1),
                               repayment_start_date=date.fromisoformat(old_due),
                               current_principal_amount=80000, monthly_repayment_amount=800,
                               broken_period_interest=0, loan_disbursement='OLD',
                               total_installments_raised=1, total_installments_paid=1,
                               total_installments_overdue=0, get=lambda key: [row])
    frappe.db.get_value.return_value = 'Partially Disbursed'
    frappe.get_doc = MagicMock(return_value=previous)
    schedule.is_dcr_floorplan_structure = lambda: True
    schedule.loan = 'DEMO'; schedule.loan_amount = 225000; schedule.loan_product = 'Standard'
    schedule.loan_disbursement = None; schedule.loan_restructure = 'RESTRUCTURE'
    schedule.current_principal_amount = 10000; schedule.disbursed_amount = 10000
    schedule.repayment_schedule_type = 'Monthly as per repayment start date'
    schedule.repayment_frequency = 'Monthly'; schedule.restructure_type = None
    schedule.repayment_method = 'Repay Fixed Amount per Period'
    schedule.repayment_start_date = date.fromisoformat(due)
    schedule.posting_date = date.fromisoformat(posting)
    schedule.moratorium_end_date = None; schedule.rate_of_interest = 12
    schedule.get_contract_interest_rate = lambda: 12
    schedule.broken_period_interest = 0
    saved = {'repayment_schedule': []}
    schedule.get = lambda key: saved[key]
    schedule.append = lambda key, values: saved[key].append(SimpleNamespace(**values))

    def add_row(payment_date, principal, interest, charges, total, balance, days,
                demand_generated=0, repayment_schedule_field='repayment_schedule', **kwargs):
        schedule.append(repayment_schedule_field, dict(payment_date=payment_date,
                        principal_amount=principal, interest_amount=interest, total_payment=total,
                        balance_loan_amount=balance, number_of_days=days,
                        demand_generated=demand_generated))
    schedule.add_repayment_schedule_row = add_row
    schedule.get_loan_product_value = lambda *names: 12 if 'custom_interest_only_months' in names else 1
    return schedule, frappe, row, saved


def test_partial_funding_carries_actual360_on_previous_balance_and_preserves_history():
    schedule, _, old, saved = fixture()
    carry, balance, _, days = schedule.add_rows_from_prev_disbursement('repayment_schedule',100)
    assert carry == 400  # 80,000 * 12% * 15 / 360
    assert balance == 90000  # 80,000 remaining + 10,000 new funding
    assert days == 15
    assert old.balance_loan_amount == 80000
    assert saved['repayment_schedule'][0].balance_loan_amount == 80000
    assert saved['repayment_schedule'][0].demand_generated == 1


def test_second_funding_before_first_due_splits_old_and_combined_interest_once():
    schedule, frappe, _, saved = fixture(old_due='2026-02-01', due='2026-02-01', posting='2026-01-16')
    # The first funding was on January 1, before any installment.
    frappe.get_doc.return_value.posting_date = date(2026,1,1)
    carry, balance, additional, days = schedule.add_rows_from_prev_disbursement('repayment_schedule',100)
    assert (carry, balance, additional, days) == (400,90000,10000,15)
    frappe.db.get_value.return_value = 225000
    schedule.make_repayment_schedule('repayment_schedule',carry,balance,additional,days,12,100,100)
    first = saved['repayment_schedule'][0]
    assert first.interest_amount == 880  # 400 old + 480 combined balance for 16 days
    assert first.principal_amount == 0


def test_future_rows_start_after_appended_pre_payment_due_without_double_interest():
    schedule, frappe, _, saved = fixture()
    saved['repayment_schedule'] = [SimpleNamespace(payment_date=date(2026,2,1))]
    schedule.repayment_start_date = date(2026,3,1)
    schedule.current_principal_amount = 90000
    frappe.db.get_value.return_value = 225000
    schedule.make_repayment_schedule('repayment_schedule',0,90000,0,0,12,100,100)
    assert saved['repayment_schedule'][1].number_of_days == 28
    assert saved['repayment_schedule'][1].interest_amount == 840


def test_pre_payment_preserves_native_adjustment_and_skipped_demand_without_rate_scaling():
    schedule, frappe, _, saved = fixture(old_due='2026-02-01')
    schedule.restructure_type = 'Pre Payment'
    schedule.current_principal_amount = 5000
    schedule.get_next_payment_date = lambda value: date(value.year, value.month+1, 1)
    schedule.get_prev_schedule_demand_generated = lambda *args: 1
    # Prepayment is before first due, so native cycle-date helper is used.
    native = schedule.add_rows_from_prev_disbursement.__globals__['native_schedule']
    native.get_cyclic_date = lambda *args, **kwargs: date(2026,2,1)
    frappe.db.get_value.side_effect = lambda doctype, *args: (300,100) if doctype == 'Loan Restructure' else 'Disbursed'
    carry, balance, _, _ = schedule.add_rows_from_prev_disbursement('repayment_schedule',100)
    first = saved['repayment_schedule'][0]
    assert first.interest_amount == pytest.approx(226.66666667)  # 26.67 new + 200 unpaid, unchanged
    assert first.principal_amount == 0  # Still within twelve IO installments
    assert first.demand_generated == 1
    assert (carry,balance) == (0,5000)
    assert schedule.rate_of_interest == 12
    frappe.db.get_value.side_effect = None
    frappe.db.get_value.return_value = 225000
    schedule.make_repayment_schedule('repayment_schedule',carry,balance,0,0,12,100,100)
    assert saved['repayment_schedule'][1].interest_amount == 46.67  # February only


def test_normal_restructure_retains_phase_and_adds_adjusted_interest_only_once():
    schedule, frappe, old, saved = fixture(posting='2027-01-16',due='2027-02-01')
    schedule.restructure_type = 'Normal Restructure'
    schedule.current_principal_amount = 5000
    schedule.adjusted_interest = 100
    previous = frappe.get_doc.return_value
    previous.get = lambda key: [SimpleNamespace(**{**vars(old), 'payment_date': date(2026,month,1)})
                                for month in range(1,13)]
    carry, balance, _, _ = schedule.add_rows_from_prev_disbursement('repayment_schedule',100)
    frappe.db.get_value.return_value = 225000
    schedule.make_repayment_schedule('repayment_schedule',carry,balance,0,0,12,100,100)
    assert [row.principal_amount for row in saved['repayment_schedule']] == [2250,2250,500]
    assert saved['repayment_schedule'][0].interest_amount == 126.67
    assert saved['repayment_schedule'][1].interest_amount == 25.67


def test_advance_payment_keeps_actual_adjustment_and_carries_remaining_days_once():
    schedule, frappe, _, saved = fixture(old_due='2026-02-01')
    schedule.restructure_type = 'Advance Payment'
    frappe.get_doc.return_value.posting_date = date(2026,1,1)
    schedule.current_principal_amount = 5000
    schedule.monthly_repayment_amount = 300
    schedule.get_next_payment_date = lambda value: date(value.year,value.month+1,1)
    def value(doctype, name, field):
        if doctype == 'Loan Restructure':
            return 100 if field == 'adjusted_unaccrued_interest' else date(2026,3,1)
        return 'Disbursed'
    frappe.db.get_value.side_effect = value
    carry, balance, _, days = schedule.add_rows_from_prev_disbursement('repayment_schedule',100)
    advance = saved['repayment_schedule'][0]
    assert (advance.principal_amount,advance.interest_amount,advance.balance_loan_amount) == (200,100,5000)
    assert (balance,days) == (5000,16)
    assert carry == pytest.approx(26.66666667)
    frappe.db.get_value.side_effect = None
    frappe.db.get_value.return_value = 225000
    schedule.make_repayment_schedule('repayment_schedule',carry,balance,0,days,12,100,100)
    assert saved['repayment_schedule'][1].interest_amount == 73.33
