"""Keyboard-created blank rows must not reach native typed charge calculation."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class Row(SimpleNamespace):
    def get(self, field, default=None):
        return getattr(self, field, default)


@pytest.fixture
def repayment():
    class Native(Row):
        def set(self, field, value):
            setattr(self, field, value)

        def validate(self):
            self.native_codes = [row.get('charge_code') for row in self.payable_charges]
            if any(not isinstance(code, str) for code in self.native_codes):
                raise TypeError('charges must contain strings')

    previous = sys.modules.pop('dcr.overrides.loan_repayment', None)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment':
            SimpleNamespace(LoanRepayment=Native),
    }):
        module = importlib.import_module('dcr.overrides.loan_repayment')
        with patch.object(module, 'frappe') as frappe, \
                patch.object(module, 'flt', side_effect=lambda value: float(value or 0)):
            frappe.db.get_value.return_value = None
            def throw(message):
                raise ValueError(message)
            frappe.throw.side_effect = throw
            try:
                yield module.CustomLoanRepayment
            finally:
                sys.modules.pop('dcr.overrides.loan_repayment', None)
                if previous is not None:
                    sys.modules['dcr.overrides.loan_repayment'] = previous


@pytest.mark.parametrize('kind,restructure', [
    ('Charge Payment', None), ('Charges Waiver', 'RESTRUCTURE'),
    ('Charges Capitalization', 'RESTRUCTURE'),
])
def test_tab_placeholder_does_not_break_a_valid_charge_selection(repayment, kind, restructure):
    first = Row(name='FIRST', idx=1, charge_code='DCR Financing Fee', amount=50)
    second = Row(name='SECOND', idx=3, charge_code='Other Fee', amount=10)
    doc = repayment(repayment_type=kind, loan_restructure=restructure, against_loan='LOAN',
        payable_charges=[first, Row(idx=2, charge_code=None, amount=0), second,
                         Row(idx=4, charge_code='', amount='0.00')])
    doc.validate()
    assert doc.native_codes == ['DCR Financing Fee', 'Other Fee']
    assert doc.payable_charges == [first, second]
    assert [(r.name, r.idx, r.amount) for r in doc.payable_charges] == [
        ('FIRST', 1, 50), ('SECOND', 2, 10)]


@pytest.mark.parametrize('amount', [25, -25])
def test_entered_amount_without_a_code_has_actionable_row_feedback(repayment, amount):
    doc = repayment(repayment_type='Charge Payment', against_loan='LOAN',
        payable_charges=[Row(idx=1, charge_code=None, amount=amount)])
    with pytest.raises(ValueError, match='Payable Charges row 1.*Charge Code'):
        doc.validate()
    assert doc.payable_charges[0].amount == amount
    assert not hasattr(doc, 'native_codes')


def test_all_blank_placeholders_leave_native_allocation_to_check_the_payment(repayment):
    doc = repayment(repayment_type='Charge Payment', against_loan='LOAN',
        payable_charges=[Row(idx=1, charge_code='', amount=0)])
    doc.validate()
    assert doc.native_codes == doc.payable_charges == []


@pytest.mark.parametrize('kind', ['Normal Repayment', 'Charges Waiver', 'Charges Capitalization'])
def test_unsupported_charge_tables_keep_native_validation(repayment, kind):
    doc = repayment(repayment_type=kind, against_loan='LOAN',
        payable_charges=[Row(idx=1, charge_code=None, amount=0)])
    with pytest.raises(TypeError, match='charges must contain strings'):
        doc.validate()
    assert len(doc.payable_charges) == 1
