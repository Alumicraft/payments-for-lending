"""Offline check against the installed Lending source pin; never connects to Frappe.

Pass an extracted Lending source directory. Hash checks intentionally fail when
the provider changes so its entry gate and prepayment behavior are reviewed again.
Documents here record save/submit calls in memory; they do not prove hosted GL.
"""

import argparse
import ast
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dcr.lending_rules import floorplan_interval_interest, principal_on_day


def load_function(path, name, namespace, class_name=None):
    tree = ast.parse(path.read_text())
    nodes = tree.body
    if class_name:
        nodes = next(node.body for node in nodes if isinstance(node, ast.ClassDef)
                     and node.name == class_name)
    function = next(node for node in nodes if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


def flt(value, precision=2):
    return float(Decimal(str(value or 0)).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP))


def verify(root):
    paths = {
        'loan_interest_accrual': '0af3eb36dab0c0ba184caaa1a0412e9187a08d2e697b01be613290be524baecc',
        'loan_repayment_schedule': '8ae00a7598f0a8becee4459fafee9f5e968b22ae44b8d641aaab2f2c7b46cf33',
        'loan_repayment': 'de9ef9fe1959abcd24f0efa2543d30719f285e21737825a8687778c1ec35861a',
    }
    source = {}
    for name, expected in paths.items():
        path = root / 'lending/loan_management/doctype' / name / (name+'.py')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'Review changed native source: {path}'
        source[name] = path

    posted = []

    class Accrual(SimpleNamespace):
        def save(self):
            self.saved = True

        def submit(self):
            assert self.saved
            posted.append(self)

    frappe = SimpleNamespace(db=SimpleNamespace(get_default=lambda key: 2),
        flags=SimpleNamespace(on_repost=False), new_doc=lambda kind: Accrual())
    namespace = dict(frappe=frappe, cint=int, flt=flt)
    entry = load_function(source['loan_interest_accrual'], 'make_loan_interest_accrual_entry', namespace)
    native = SimpleNamespace(make_loan_interest_accrual_entry=entry,
                             get_principal_amount_for_term_loan=lambda *args: 0)
    events = [('2026-11-01', 225000), ('2027-12-01', -2250),
              ('2028-01-01', -2250), ('2028-01-15', -5000)]
    contract = SimpleNamespace(rate_of_interest=12)
    adapter_scope = dict(contextmanager=contextmanager, timedelta=timedelta,
        getdate=lambda value: date.fromisoformat(str(value)[:10]),
        floorplan_loan=lambda name: contract, principal_events=lambda loan: events,
        first_payment_date=lambda loan: '2026-12-01', principal_on_day=principal_on_day,
        floorplan_interval_interest=floorplan_interval_interest)
    adapter = load_function(Path(__file__).resolve().parents[2] / 'dcr/api/floorplan_accrual.py',
                            'actual_principal_accruals', adapter_scope)

    def month():
        posted.clear()
        for offset in range(31):
            day = date(2028, 1, 1) + timedelta(days=offset)
            principal = principal_on_day(events, day)
            native.make_loan_interest_accrual_entry('LOAN', float(principal),
                float(principal * Decimal(12) / Decimal(36000)), 'PROCESS', day, day,
                'Regular', 'Normal Interest', 12)
        return sum(Decimal(str(row.interest_amount)) for row in posted)

    old = month()
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_interest_accrual':
            SimpleNamespace(loan_interest_accrual=native)}):
        with adapter():
            corrected = month()
            events = [('2026-11-01', 1)]
            tiny = month()
    assert native.make_loan_interest_accrual_entry is entry
    assert (old, corrected, tiny) == (Decimal('2250.11'), Decimal('2250.17'), Decimal('0.01'))

    demands = []
    details = SimpleNamespace(unaccrued_interest=1029, adjusted_unaccrued_interest=0,
                               balance_principal=-5000, loan_repayment='RECEIPT')
    frappe.db.get_value = lambda *args, **kwargs: details
    scope = dict(frappe=frappe, cint=int, flt=flt,
        create_loan_demand=lambda *args, **kwargs: demands.append((args[3], args[4], kwargs['paid_amount'])),
        add_days=lambda day, offset: date.fromisoformat(str(day)[:10])+timedelta(days=offset))
    method = load_function(source['loan_repayment_schedule'], 'make_demand_for_advance_payment',
                            scope, 'LoanRepaymentSchedule')
    schedule = SimpleNamespace(restructure_type='Pre Payment', loan='LOAN', loan_restructure='RESTRUCTURE',
        repayment_schedule=[SimpleNamespace(demand_generated=0, name='NEXT')], name='SCHEDULE',
        posting_date='2028-01-15', loan_disbursement=None, company='DCR', rate_of_interest=12,
        current_principal_amount=215500, number_of_rows=98, moratorium_tenure=0,
        is_dcr_floorplan_structure=lambda: True)
    native.get_interest_for_term = lambda *args: 0
    native.get_last_accrual_date = lambda *args: '2028-01-14'
    native_modules = {
        'lending.loan_management.doctype.loan_interest_accrual.loan_interest_accrual': native,
        'lending.loan_management.doctype.loan_demand.loan_demand':
            SimpleNamespace(create_loan_demand=scope['create_loan_demand']),
        'lending.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual':
            SimpleNamespace(process_loan_interest_accrual_for_loans=lambda **kwargs: None),
        'frappe.utils': SimpleNamespace(add_days=scope['add_days']),
    }
    with patch.dict(sys.modules, native_modules):
        method(schedule)
        assert demands == [('Interest', 1029, 1029), ('Principal', 5000, 5000)]
        demands.clear()
        custom = load_function(Path(__file__).resolve().parents[2] / 'dcr/overrides/loan_repayment_schedule.py',
            'make_demand_for_advance_payment', scope, 'CustomLoanRepaymentSchedule')
        custom(schedule)
        assert demands == [('Principal', 5000.0, 5000.0)]
    print('Pinned native factory: daily total 2250.11 -> 2250.17; sub-cent month -> 0.01.')
    print('Pinned native prepayment: false paid interest 1029.00 -> 0.00; paid principal stays 5000.00.')
    verify_allocation(source['loan_repayment'])
    print('Offline source check only. Hosted posting, ledger and reversal acceptance remain separate.')


def verify_allocation(source):
    def reject(message):
        raise ValueError(message)

    frappe = SimpleNamespace(db=SimpleNamespace(get_default=lambda key: 2,
        get_value=lambda *args: 'Disbursed'), throw=reject)
    scope = dict(frappe=frappe, flt=flt, cint=int)
    class Native(SimpleNamespace):
        def get(self, key, default=None):
            return getattr(self, key, default)

        def set(self, key, value):
            setattr(self, key, value)

        def hard_clear_table(self):
            self.repayment_details = []

        def update_amounts_for_write_off_recovery(self, status, amounts):
            return amounts

        def allocate_amount_against_demands(self, status, amounts, cash):
            assert not amounts['unpaid_demands']
            return cash

        def handle_final_closure_payments(self, amounts):
            pass

    for method in ('allocate_amounts', 'init_amounts'):
        setattr(Native, method, load_function(source, method, scope, 'LoanRepayment'))
    amounts = dict(unaccrued_interest=1029, unbooked_interest=0,
                   unbooked_penalty=0, unpaid_demands=[], pending_principal_amount=220500)
    values = dict(repayment_type='Pre Payment', against_loan='LOAN', amount_paid=5000,
                  total_charges_payable=0, is_imported=False)
    old = Native(**values)
    old.allocate_amounts(amounts)
    assert (old.principal_amount_paid, old.total_interest_paid) == (3971, 1029)
    path = Path(__file__).resolve().parents[2] / 'dcr/overrides/loan_repayment.py'
    with patch.dict(sys.modules, {
        'frappe': frappe, 'frappe.utils': SimpleNamespace(flt=flt, cint=int),
        'lending.loan_management.doctype.loan_repayment.loan_repayment': SimpleNamespace(LoanRepayment=Native),
        'dcr.api.floorplan_accrual': SimpleNamespace(floorplan_loan=lambda name: SimpleNamespace()),
    }):
        spec = importlib.util.spec_from_file_location('allocation_diagnostic', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for on_submit in (False, True):
            doc = module.CustomLoanRepayment(**values)
            doc.allocate_amounts(amounts, on_submit=on_submit)
            assert (doc.principal_amount_paid, doc.total_interest_paid, doc.unbooked_interest_paid) == (5000, 0, 0)
        doc = module.CustomLoanRepayment(**dict(values, amount_paid=220500))
        try:
            doc.allocate_amounts(amounts)
        except ValueError as error:
            assert 'Loan Closure' in str(error)
        else:
            raise AssertionError('A principal-only payment must not close a loan with earned interest.')
    assert amounts['unaccrued_interest'] == 1029
    print('Pinned native allocation on draft/submit: 3971 principal + 1029 interest -> 5000 principal; payoff uses Closure.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lending_source', type=Path)
    verify(parser.parse_args().lending_source)
