from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys

import pytest

from dcr.api import floorplan_accrual, lending


class Doc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


@contextmanager
def demand_context(booked=38594.25, demanded=38594.25, latest='2028-02-29', payments=()):
    loan = Doc(name='LOAN', loan_product='Standard', company='DCR',
               original_financed_principal=225000, home_build_request='HOME', rate_of_interest=12)
    created = []

    def new_doc(doctype):
        assert doctype == 'Loan Demand'
        doc = Doc(save=Mock(), submit=Mock())
        created.append(doc)
        return doc

    def get_all(doctype, filters, fields, **kwargs):
        assert filters['docstatus'] == 1
        if doctype == 'Loan Disbursement':
            return [Doc(disbursement_date='2026-10-01', disbursed_amount=225000)]
        if doctype == 'Loan Repayment':
            return [Doc(value_date=day, principal_amount_paid=amount) for day, amount in (
                ('2027-11-01', 2250), ('2027-12-01', 2250), ('2028-02-01', 2250), *payments)]
        if doctype == 'Loan Interest Accrual':
            if fields == ['sum(interest_amount) as amount']:
                return [Doc(amount=booked)]
            assert fields == ['posting_date']
            return [Doc(posting_date=latest)] if latest else []
        assert doctype == 'Loan Demand'
        assert fields == ['sum(demand_amount) as amount']
        assert filters['demand_subtype'] == 'Interest'
        return [Doc(amount=demanded)]

    with patch.object(lending, 'frappe') as frappe, \
            patch.object(floorplan_accrual, 'frappe', frappe), \
            patch.object(floorplan_accrual, 'product_terms', return_value={
                'schedule_type': 'Interest Only Then Percent Principal'}), \
            patch.object(lending, 'populate_loan_demand_from_loan'), \
            patch.object(sys.modules['frappe.utils'], 'cint', side_effect=int), \
            patch.object(sys.modules['frappe.utils'], 'flt',
                         side_effect=lambda value, precision=2: round(float(value or 0), precision)):
        frappe.get_doc.return_value = loan
        frappe.db.get_value.return_value = 'Daily'
        frappe.db.get_default.return_value = 2
        frappe.get_all.side_effect = get_all
        frappe.new_doc.side_effect = new_doc
        yield SimpleNamespace(created=created, loan=loan, frappe=frappe)


def issue(**changes):
    values = dict(loan='LOAN', demand_date='2028-04-01', demand_type='EMI',
                  demand_subtype='Interest', amount=2232,
                  loan_repayment_schedule='SCHEDULE', repayment_schedule_detail='APRIL',
                  process_loan_demand='PROCESS')
    values.update(changes)
    lending.create_loan_demand_with_context(**values)


def test_unpaid_month_does_not_assume_forecast_principal_was_received():
    with demand_context() as context:
        issue()
        assert context.created[0].demand_amount == 2255.25
        context.created[0].save.assert_called_once()
        context.created[0].submit.assert_called_once()


@pytest.mark.parametrize('payments,expected', [
    ((('2028-03-01', 2250),), 2232),
    ((('2028-03-01', 1000),), 2245.02),
    ((('2028-03-16', 2250),), 2243.25),
])
def test_actual_principal_payment_amount_and_value_date_determine_interest(payments, expected):
    with demand_context(payments=payments) as context:
        issue()
        assert context.created[0].demand_amount == expected


def test_previously_booked_days_are_not_accrued_or_counted_again():
    with demand_context(booked=40849.50, latest='2028-03-31') as context:
        issue()
        assert context.created[0].demand_amount == 2255.25


def test_prior_restructure_carry_is_earned_once_without_repricing_old_days():
    with demand_context(booked=35235, demanded=31927.50, latest='2028-01-14') as context:
        issue(demand_date='2028-02-01', amount=4557)
        assert context.created[0].demand_amount == 4557


def test_a_generated_waiver_demand_is_not_billed_again_at_month_end():
    with demand_context(demanded=38667) as context:
        issue()
        assert context.created[0].demand_amount == 2182.50


def test_already_demanded_interest_does_not_create_a_second_or_negative_demand():
    with demand_context(booked=40849.50, demanded=40849.50, latest='2028-03-31') as context:
        issue()
        assert context.created == []
    with demand_context(demanded=50000) as context:
        issue()
        assert context.created == []


@pytest.mark.parametrize('due,already_demanded,expected', [
    ('2026-11-01', 0, 2325), ('2026-12-01', 2325, 2250),
    ('2027-01-01', 4575, 2325), ('2027-02-01', 6900, 2325),
    ('2027-03-01', 9225, 2100), ('2027-04-01', 11325, 2325),
    ('2027-05-01', 13650, 2250), ('2027-06-01', 15900, 2325),
    ('2027-07-01', 18225, 2250), ('2027-08-01', 20475, 2325),
    ('2027-09-01', 22800, 2325), ('2027-10-01', 25125, 2250),
])
def test_twelve_interest_only_demands_use_actual_days(due, already_demanded, expected):
    with demand_context(booked=0, demanded=already_demanded, latest=None) as context:
        issue(demand_date=due, amount=expected)
        assert context.created[0].demand_amount == expected


@pytest.mark.parametrize('changes', [
    {'original_financed_principal': 0}, {'home_build_request': None},
])
def test_legacy_loans_keep_the_native_forecast(changes):
    with demand_context() as context:
        for key, value in changes.items():
            setattr(context.loan, key, value)
        issue()
        assert context.created[0].demand_amount == 2232
        context.frappe.get_all.assert_not_called()


@pytest.mark.parametrize('changes', [
    {'demand_subtype': 'Principal'}, {'demand_type': 'BPI'},
    {'repayment_schedule_detail': None}, {'process_loan_demand': None},
    {'loan_repayment': 'RECEIPT'}, {'is_imported': True}, {'paid_amount': 2232},
    {'is_partial_pre_paid_interest': True},
])
def test_non_monthly_or_already_paid_demands_keep_native_handling(changes):
    with demand_context() as context:
        issue(**changes)
        assert context.created[0].demand_amount == 2232
        context.frappe.get_all.assert_not_called()
