"""A Charge Payment must never spill an unmatched amount into principal."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def repayment():
    calls = []

    class Native:
        def allocate_charges(self, amount_paid, demands):
            calls.append((amount_paid, demands))
            return self.unallocated

    previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':
            SimpleNamespace(LoanRepayment=Native),
    }):
        module = importlib.import_module('dcr.overrides.loan_repayment')
        with patch.object(module, 'frappe') as frappe, \
                patch.object(module, 'flt', side_effect=lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)), \
                patch.object(module, 'cint', side_effect=lambda value: int(value or 0)):
            frappe.db.get_default.return_value = '2'
            def throw(message):
                raise ValueError(message)

            frappe.throw.side_effect = throw
            doc = module.CustomLoanRepayment()
            doc.repayment_type = 'Charge Payment'
            try:
                yield doc, calls
            finally:
                sys.modules.pop('dcr.overrides.loan_repayment', None)
                if previous is not None:
                    sys.modules['dcr.overrides.loan_repayment'] = previous


@pytest.mark.parametrize('unallocated', [25, 5, 0.01])
def test_unselected_or_underallocated_charge_payment_is_rejected(repayment, unallocated):
    doc, calls = repayment
    doc.unallocated = unallocated
    demands = [SimpleNamespace(name='CHARGE', outstanding_amount=25)]
    with pytest.raises(ValueError, match='Payable Charges'):
        doc.allocate_charges(25, demands)
    assert calls == [(25, demands)]


@pytest.mark.parametrize('unallocated', [0, 0.004])
def test_fully_allocated_charge_payment_keeps_native_result(repayment, unallocated):
    doc, calls = repayment
    doc.unallocated = unallocated
    assert doc.allocate_charges(25, ['CHARGE']) == unallocated
    assert calls == [(25, ['CHARGE'])]


@pytest.mark.parametrize('kind', ['Charges Waiver', 'Charges Capitalization'])
def test_restructure_charge_operations_keep_native_remainder_handling(repayment, kind):
    doc, calls = repayment
    doc.repayment_type = kind
    doc.unallocated = 5
    assert doc.allocate_charges(25, ['CHARGE']) == 5
    assert calls == [(25, ['CHARGE'])]
