"""Cancelling a charge receipt or waiver must undo its paid counters."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def cancellation():
    rows = {
        'Loan': dict(name='LOAN', total_amount_paid=6832, total_principal_paid=2250,
                     status='Disbursed'),
        'Loan Disbursement': dict(name='DISBURSEMENT', principal_amount_paid=6750),
    }
    events = []

    class Field:
        def __init__(self, name):
            self.name = name

        def __sub__(self, amount):
            return lambda row: row[self.name] - amount

        def __eq__(self, value):
            return lambda row: row[self.name] == value

    class Table:
        def __init__(self, name):
            self.table_name = name

        def __getattr__(self, name):
            return Field(name)

    class Query:
        def __init__(self, table):
            self.table = table
            self.changes = {}

        def set(self, field, value):
            self.changes[field.name] = value
            return self

        def where(self, predicate):
            self.predicate = predicate
            return self

        def run(self):
            row = rows[self.table.table_name]
            assert self.predicate(row)
            values = {key: value(row) if callable(value) else value
                      for key, value in self.changes.items()}
            row.update(values)

    class Native:
        def mark_as_unpaid(self):
            events.append('native cancellation')
            return 'native result'

        def update_limits(self, query, loan, cancel=0):
            events.append(('limits', cancel))
            return query

    previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':
            SimpleNamespace(LoanRepayment=Native),
    }):
        module = importlib.import_module('dcr.overrides.loan_repayment')
        with patch.object(module, 'frappe') as frappe:
            frappe.qb.DocType.side_effect = Table
            frappe.qb.update.side_effect = Query
            doc = module.CustomLoanRepayment()
            doc.against_loan = 'LOAN'
            doc.loan_disbursement = None
            doc.amount_paid = 25
            doc.principal_amount_paid = 0
            try:
                yield doc, rows, events
            finally:
                sys.modules.pop('dcr.overrides.loan_repayment', None)
                if previous is not None:
                    sys.modules['dcr.overrides.loan_repayment'] = previous


@pytest.mark.parametrize('kind', ['Charge Payment', 'Charges Waiver'])
def test_charge_cancellation_restores_paid_counters(cancellation, kind):
    doc, rows, events = cancellation
    doc.repayment_type = kind
    doc.mark_as_unpaid()
    assert rows['Loan'] == dict(name='LOAN', total_amount_paid=6807,
                               total_principal_paid=2250, status='Disbursed')
    assert events == [('limits', 1)]


def test_old_charge_principal_allocation_and_disbursement_also_reverse(cancellation):
    doc, rows, _ = cancellation
    doc.repayment_type = 'Charge Payment'
    doc.loan_disbursement = 'DISBURSEMENT'
    doc.principal_amount_paid = 25
    rows['Loan'].update(total_principal_paid=2275, status='Closed')
    rows['Loan Disbursement']['principal_amount_paid'] = 6775
    doc.mark_as_unpaid()
    assert rows['Loan']['total_amount_paid'] == 6807
    assert rows['Loan']['total_principal_paid'] == 2250
    assert rows['Loan']['status'] == 'Closed'
    assert rows['Loan Disbursement']['principal_amount_paid'] == 6750


def test_other_repayment_cancellation_stays_native(cancellation):
    doc, rows, events = cancellation
    doc.repayment_type = 'Normal Repayment'
    assert doc.mark_as_unpaid() == 'native result'
    assert events == ['native cancellation']
    assert rows['Loan']['total_amount_paid'] == 6832
