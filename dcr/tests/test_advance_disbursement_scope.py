"""Reject an obsolete disbursement scope before native repayment calculation."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class Record(SimpleNamespace):
    def get(self, field, default=None):
        return getattr(self, field, default)


@pytest.fixture
def repayment():
    class Native(Record):
        def validate(self):
            self.native_validated = True

    previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':
            SimpleNamespace(LoanRepayment=Native),
        'lending.loan_management.doctype.loan_interest_accrual':
            SimpleNamespace(loan_interest_accrual=SimpleNamespace(
                get_principal_amount_for_term_loan=lambda *args: 0)),
    }):
        module = importlib.import_module('dcr.overrides.loan_repayment')
        with patch.object(module, 'frappe') as frappe, \
                patch('dcr.api.floorplan_accrual.floorplan_loan') as floorplan:
            frappe.db.get_value.return_value = None
            floorplan.return_value = Record(name='LOAN', repayment_schedule_type='Monthly as per cycle date')
            def exists(doctype, filters):
                return filters.get('loan_disbursement') == ['is', 'not set']
            frappe.db.exists.side_effect = exists
            def throw(message):
                raise ValueError(message)
            frappe.throw.side_effect = throw
            doc = module.CustomLoanRepayment(repayment_type='Advance Payment', against_loan='LOAN',
                                            loan_disbursement='DISBURSEMENT')
            try:
                yield doc, frappe, floorplan
            finally:
                sys.modules.pop('dcr.overrides.loan_repayment', None)
                if previous is not None:
                    sys.modules['dcr.overrides.loan_repayment'] = previous


@pytest.mark.parametrize('kind', ['Advance Payment', 'Pre Payment'])
def test_loan_wide_schedule_rejects_an_obsolete_disbursement_scope(repayment, kind):
    doc, frappe, _ = repayment
    doc.repayment_type = kind
    with pytest.raises(ValueError, match='Clear Loan Disbursement'):
        doc.validate()
    assert not doc.get('native_validated')
    assert doc.loan_disbursement == 'DISBURSEMENT'
    for call in frappe.db.exists.call_args_list:
        assert call.args[0] == 'Loan Repayment Schedule'
        assert call.args[1]['loan'] == 'LOAN'
        assert call.args[1]['docstatus'] == 1
        assert call.args[1]['status'] == 'Active'


@pytest.mark.parametrize('scope', ['matching', 'blank', 'native', 'line-of-credit', 'imported', 'no-active'])
def test_supported_scopes_keep_native_validation(repayment, scope):
    doc, frappe, floorplan = repayment
    if scope == 'matching':
        frappe.db.exists.side_effect = lambda doctype, filters: filters.get('loan_disbursement') == 'DISBURSEMENT'
    elif scope == 'blank':
        doc.loan_disbursement = None
    elif scope == 'native':
        floorplan.return_value = None
    elif scope == 'line-of-credit':
        floorplan.return_value.repayment_schedule_type = 'Line of Credit'
    elif scope == 'imported':
        doc.is_imported = 1
    elif scope == 'no-active':
        frappe.db.exists.side_effect = None
        frappe.db.exists.return_value = False
    doc.validate()
    assert doc.native_validated


def test_normal_repayment_is_outside_this_advance_payment_repair(repayment):
    doc, _, floorplan = repayment
    doc.repayment_type = 'Normal Repayment'
    doc.validate()
    assert doc.native_validated
    floorplan.assert_not_called()
