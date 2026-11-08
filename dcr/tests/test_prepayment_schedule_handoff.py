"""A schedule built during validation must use the current unsaved interest."""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.parametrize('balance', [0, 1029])
@pytest.mark.parametrize('kind,eligible', [('Pre Payment', True), ('Normal Restructure', True),
                                         ('Pre Payment', False)])
def test_schedule_details_include_current_interest_only_for_dcr_prepayment(balance, kind, eligible):
    class Native(SimpleNamespace):
        def get_schedule_details(self, adjusted_interest=0):
            return {'loan': self.loan, 'adjusted_interest': adjusted_interest}

    name = 'dcr.overrides.loan_restructure'
    previous = sys.modules.pop(name, None)
    try:
        with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_restructure.loan_restructure':
                SimpleNamespace(LoanRestructure=Native),
        }):
            module = importlib.import_module(name)
            with patch.object(module, 'floorplan_loan', return_value=object() if eligible else None):
                doc = module.CustomLoanRestructure(loan='LOAN', restructure_type=kind,
                                                  balance_unaccrued_interest=balance)
                details = doc.get_schedule_details(45)
                assert details['loan'] == 'LOAN'
                assert details['adjusted_interest'] == 45
                if kind == 'Pre Payment' and eligible:
                    assert details['_dcr_balance_unaccrued_interest'] == balance
                else:
                    assert '_dcr_balance_unaccrued_interest' not in details
    finally:
        sys.modules.pop(name, None)
        if previous is not None:
            sys.modules[name] = previous
