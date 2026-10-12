"""Waiving undemanded interest must not invent a cash payment or survive cancellation."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def trial():
    demands = [
        dict(name='EXISTING', loan='LOAN', loan_repayment=None, docstatus=1,
             demand_subtype='Interest', paid_amount=0, waived_amount=10, outstanding_amount=20),
        dict(name='OTHER', loan='OTHER-LOAN', loan_repayment='WAIVER', docstatus=1,
             demand_subtype='Interest', paid_amount=30, waived_amount=0, outstanding_amount=0),
    ]
    events = []

    class Native:
        def book_interest_accrued_not_demanded(self):
            events.append('native book')
            demands.append(dict(name='GENERATED', loan=self.against_loan, loan_repayment=self.name,
                                docstatus=1, demand_subtype='Penalty' if self.repayment_type == 'Penalty Waiver' else 'Interest',
                                paid_amount=72.75, waived_amount=0, outstanding_amount=0))

        def on_cancel(self):
            events.append('native cancel')

    previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_repayment.loan_repayment':
                                SimpleNamespace(LoanRepayment=Native)}), \
            patch('dcr.api.floorplan_accrual.floorplan_loan', return_value=True) as scoped:
        module = importlib.import_module('dcr.overrides.loan_repayment')
        with patch.object(module, 'frappe') as frappe:
            def get_all(doctype, filters, fields=None, pluck=None):
                assert doctype == 'Loan Demand'
                matches = [d for d in demands if all(d.get(k) == v for k, v in filters.items())]
                return [d[pluck] if pluck else SimpleNamespace(**{k:d[k] for k in fields}) for d in matches]

            def set_value(doctype, name, values, **kwargs):
                assert doctype == 'Loan Demand'
                next(d for d in demands if d['name'] == name).update(values)

            def get_doc(doctype, name):
                assert doctype == 'Loan Demand'
                def cancel():
                    events.append(('cancel demand', name))
                    next(d for d in demands if d['name'] == name)['docstatus'] = 2
                return SimpleNamespace(cancel=cancel)

            frappe.get_all.side_effect = get_all
            frappe.db.set_value.side_effect = set_value
            frappe.get_doc.side_effect = get_doc
            doc = module.CustomLoanRepayment()
            doc.name = 'WAIVER'; doc.against_loan = 'LOAN'; doc.repayment_type = 'Interest Waiver'
            doc._reopen_legacy_interest_only_loan = lambda: None
            try:
                yield doc, demands, events, scoped
            finally:
                sys.modules.pop('dcr.overrides.loan_repayment', None)
                if previous is not None:
                    sys.modules['dcr.overrides.loan_repayment'] = previous


@pytest.mark.parametrize('kind', ['Interest Waiver', 'Penalty Waiver'])
def test_generated_demand_records_waiver_and_cancels_with_its_owner(trial, kind):
    doc, demands, events, _ = trial
    doc.repayment_type = kind
    doc.book_interest_accrued_not_demanded()
    generated = demands[-1]
    assert generated['paid_amount'] == 0
    assert generated['waived_amount'] == 72.75
    assert generated['outstanding_amount'] == 0
    assert demands[0]['waived_amount'] == 10
    assert demands[1]['paid_amount'] == 30
    doc.on_cancel()
    assert generated['docstatus'] == 2
    assert demands[0]['docstatus'] == demands[1]['docstatus'] == 1
    assert events == ['native book', 'native cancel', ('cancel demand', 'GENERATED')]


@pytest.mark.parametrize('kind, floorplan', [('Normal Repayment', True), ('Interest Waiver', False)])
def test_other_repayments_and_legacy_loans_keep_native_behavior(trial, kind, floorplan):
    doc, demands, events, scoped = trial
    scoped.return_value = floorplan
    doc.repayment_type = kind
    doc.book_interest_accrued_not_demanded()
    doc.on_cancel()
    assert demands[-1]['paid_amount'] == 72.75
    assert demands[-1]['waived_amount'] == 0
    assert demands[-1]['docstatus'] == 1
    assert events == ['native book', 'native cancel']
