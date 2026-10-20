from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

import pytest

from dcr.api import floorplan_accrual, lending


class Doc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


class NativeDemand(Doc):
    def is_new(self):
        return self.saved == 0

    def validate(self):
        self.outstanding_amount = self.demand_amount - self.get('paid_amount', 0)

    def save(self):
        self.validate()
        self.saved += 1

    def submit(self):
        self.docstatus = 1
        self.validate()
        self.before_submit()
        self.make_gl_entries()
        self.submitted += 1

    def make_gl_entries(self, cancel=0):
        self.gl_amounts.append(self.demand_amount)


@contextmanager
def demand_context(booked=38594.25, demanded=38594.25, latest='2028-02-29', payments=()):
    loan = Doc(name='LOAN', loan_product='Standard', company='DCR',
               original_financed_principal=225000, home_build_request='HOME', rate_of_interest=12)
    created = []
    controller = None

    def new_doc(doctype):
        assert doctype == 'Loan Demand'
        doc = controller(docstatus=0, saved=0, submitted=0, gl_amounts=[])
        created.append(doc)
        return doc

    def get_all(doctype, filters, fields, **kwargs):
        assert filters['docstatus'] == 1
        assert not any(isinstance(field, str) and '(' in field for field in fields), \
            'Frappe v16 requires structured aggregate fields'
        if doctype == 'Loan Disbursement':
            return [Doc(disbursement_date='2026-10-01', disbursed_amount=225000)]
        if doctype == 'Loan Repayment':
            return [Doc(value_date=day, principal_amount_paid=amount) for day, amount in (
                ('2027-11-01', 2250), ('2027-12-01', 2250), ('2028-02-01', 2250), *payments)]
        if doctype == 'Loan Interest Accrual':
            if fields == [{'SUM': 'interest_amount', 'as': 'amount'}]:
                return [Doc(amount=booked)]
            assert fields == ['posting_date']
            return [Doc(posting_date=latest)] if latest else []
        assert doctype == 'Loan Demand'
        assert fields == [{'SUM': 'demand_amount', 'as': 'amount'}]
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
        spec = importlib.util.spec_from_file_location('monthly_demand_controller',
            Path(__file__).parents[1] / 'overrides/loan_demand.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_demand.loan_demand':
                SimpleNamespace(LoanDemand=NativeDemand),
        }):
            spec.loader.exec_module(module)
        controller = module.CustomLoanDemand
        yield SimpleNamespace(created=created, loan=loan, frappe=frappe)


def demand_values(**changes):
    values = dict(loan='LOAN', demand_date='2028-04-01', demand_type='EMI',
                  demand_subtype='Interest', amount=2232,
                  loan_repayment_schedule='SCHEDULE', repayment_schedule_detail='APRIL',
                  process_loan_demand='PROCESS')
    values.update(changes)
    return values


def issue(**changes):
    lending.create_loan_demand_with_context(**demand_values(**changes))


def test_unpaid_month_does_not_assume_forecast_principal_was_received():
    with demand_context() as context:
        issue()
        assert context.created[0].demand_amount == 2255.25
        assert context.created[0].saved == context.created[0].submitted == 1


@pytest.mark.parametrize('save_first', [True, False])
def test_queued_native_creation_uses_the_controller_without_the_process_wrapper(save_first):
    with demand_context() as context:
        values = demand_values()
        doc = context.frappe.new_doc('Loan Demand')
        doc.demand_amount = values.pop('amount')
        for key, value in values.items():
            setattr(doc, key, value)
        if save_first:
            doc.save()
        doc.submit()
        assert doc.demand_amount == 2255.25
        assert doc.outstanding_amount == 2255.25
        assert doc.gl_amounts == [2255.25]


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


def test_already_demanded_interest_marks_the_period_without_another_gl_charge():
    with demand_context(booked=40849.50, demanded=40849.50, latest='2028-03-31') as context:
        issue()
        assert context.created[0].demand_amount == 0
        assert context.created[0].outstanding_amount == 0
        assert context.created[0].gl_amounts == []
    with demand_context(demanded=50000) as context:
        issue()
        assert context.created[0].demand_amount == 0
        assert context.created[0].gl_amounts == []


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


def test_submitted_demand_validation_does_not_rewrite_historical_amounts():
    with demand_context() as context:
        doc = context.frappe.new_doc('Loan Demand')
        values = demand_values()
        doc.demand_amount = values.pop('amount')
        for key, value in values.items():
            setattr(doc, key, value)
        doc.docstatus = 1
        doc.saved = 1
        doc.validate()
        assert doc.demand_amount == 2232
        context.frappe.get_all.assert_not_called()


def test_other_schedule_products_keep_native_handling():
    with demand_context() as context, patch.object(floorplan_accrual, 'product_terms',
                                                  return_value={'schedule_type': 'Amortizing'}):
        issue()
        assert context.created[0].demand_amount == 2232
        context.frappe.get_all.assert_not_called()


def test_first_demand_accepts_empty_database_aggregates():
    with demand_context(booked=None, demanded=None, latest=None) as context:
        issue(demand_date='2026-11-01', amount=2325)
        assert context.created[0].demand_amount == 2325
