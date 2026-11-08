import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


class Record(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


@pytest.mark.parametrize('on_submit', [False, True])
@pytest.mark.parametrize('kind,imported,eligible', [
    ('Pre Payment', False, True), ('Normal Repayment', False, True),
    ('Pre Payment', True, True), ('Pre Payment', False, False),
])
def test_unbilled_interest_does_not_consume_extra_principal(on_submit, kind, imported, eligible):
    allocate = Mock()
    class Native(Record):
        def allocate_amounts(self, amounts, on_submit=False):
            self.principal_amount_paid = 5000
            return allocate(amounts, on_submit=on_submit)
    name = 'dcr.overrides.loan_repayment'
    previous = sys.modules.pop(name, None)
    try:
        with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_repayment.loan_repayment':
                SimpleNamespace(LoanRepayment=Native),
        }):
            module = importlib.import_module(name)
            with patch('dcr.api.floorplan_accrual.floorplan_loan', return_value=Record() if eligible else None), \
                    patch.object(module, 'flt', side_effect=lambda x, precision=2: round(float(x or 0), precision)):
                demands = [dict(name='DUE', demand_subtype='Interest', outstanding_amount=50)]
                amounts = dict(unaccrued_interest=1029, unbooked_interest=100,
                               pending_principal_amount=220500, unpaid_demands=demands)
                doc = module.CustomLoanRepayment(repayment_type=kind, is_imported=imported,
                    against_loan='LOAN', amount_paid=5000)
                doc.allocate_amounts(amounts, on_submit=on_submit)
                passed = allocate.call_args.args[0]
                principal_only = kind == 'Pre Payment' and not imported and eligible
                assert passed['unaccrued_interest'] == (0 if principal_only else 1029)
                assert passed['unbooked_interest'] == (0 if principal_only else 100)
                assert passed['unpaid_demands'] is demands
                assert allocate.call_args.kwargs['on_submit'] is on_submit
                assert amounts['unaccrued_interest'] == 1029
                assert amounts['unbooked_interest'] == 100
    finally:
        sys.modules.pop(name, None)
        if previous is not None:
            sys.modules[name] = previous
