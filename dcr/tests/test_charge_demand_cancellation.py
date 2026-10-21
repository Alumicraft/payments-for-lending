"""Invoice cancellation can encounter a demand already cancelled by Cancel All."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.parametrize('status,kind,invoice_status,owner,scoped,skip', [
    (2, 'Charges', 2, 'LOAN', True, True),
    (1, 'Charges', 2, 'LOAN', True, False),
    (2, 'EMI', 2, 'LOAN', True, False),
    (2, 'Charges', 1, 'LOAN', True, False),
    (2, 'Charges', 2, 'OTHER', True, False),
    (2, 'Charges', 2, 'LOAN', False, False),
])
def test_invoice_retry_does_not_cancel_its_cancelled_charge_demand_twice(
        status, kind, invoice_status, owner, scoped, skip):
    calls = []

    class Native:
        def get(self, field, default=None):
            return getattr(self, field, default)

        def cancel(self):
            calls.append('native')
            if self.docstatus == 2:
                raise ValueError('Cannot edit cancelled document')
            self.docstatus = 2
            return self

    spec = importlib.util.spec_from_file_location('charge_demand_retry',
        Path(__file__).parents[1] / 'overrides/loan_demand.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_demand.loan_demand':
            SimpleNamespace(LoanDemand=Native),
    }):
        spec.loader.exec_module(module)
    with patch.object(module, 'frappe', create=True) as frappe, \
            patch.object(module, 'floorplan_loan', return_value=scoped, create=True):
        frappe.db.get_value.return_value = SimpleNamespace(docstatus=invoice_status, loan=owner)
        doc = module.CustomLoanDemand()
        doc.docstatus, doc.demand_type = status, kind
        doc.sales_invoice, doc.loan = 'INVOICE', 'LOAN'
        if skip or status == 1:
            assert doc.cancel() is doc
        else:
            with pytest.raises(ValueError, match='Cannot edit cancelled document'):
                doc.cancel()
        assert calls == ([] if skip else ['native'])
