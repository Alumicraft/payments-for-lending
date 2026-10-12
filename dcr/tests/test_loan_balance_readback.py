"""Funding history and pending balance diverge after native restructuring."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dcr.api import dealer_payments as payments
from dcr.api import dealer_portal as portal


@patch.object(portal, '_available_fields', side_effect=lambda doctype, fields: fields)
@patch.object(payments, 'frappe')
def test_restructured_dealer_balance_uses_native_pending_principal(frappe, fields):
    frappe.db.exists.return_value = True
    frappe.db.get_value.return_value = 'USD'
    frappe.get_all.return_value = []
    frappe.utils.today.return_value = '2026-10-11'
    loan = {'name': 'LOAN-A', 'company': 'DCR', 'status': 'Disbursed',
            'disbursed_amount': 225000, 'loan_amount': 220500,
            'total_principal_paid': 0, 'written_off_amount': 0}
    frappe.get_doc.return_value = loan
    native = MagicMock(return_value=220500)
    module = SimpleNamespace(get_pending_principal_amount=native)
    with patch.dict(sys.modules, {
        'lending.loan_management.doctype.loan_repayment.loan_repayment': module,
    }):
        result = payments.payment_summary(loan, 'DEALER-A')
    assert result['outstanding_principal'] == 220500
    native.assert_called_once_with(loan)
    assert result['funded'] is True


def test_dashboard_funding_is_posted_disbursements_not_restructured_schedule():
    import ast
    import importlib
    from pathlib import Path
    tree = ast.parse((Path(__file__).parents[1] / 'hooks.py').read_text())
    events = next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'doc_events' for t in n.targets))
    doc = MagicMock()
    values = {'name': 'LOAN-A', 'docstatus': 1, 'original_financed_principal': 225000,
              'home_build_request': 'HBR-A'}
    doc.get.side_effect = values.get
    doc.get_onload.return_value = {'total_principal': 220500, 'pending_principal': 220500, 'currency': 'USD'}
    target = events.get('Loan', {}).get('onload')
    if target:
        module_name, function_name = target.rsplit('.', 1)
        module = importlib.import_module(module_name)
        mock = MagicMock()
        mock.get_all.return_value = [SimpleNamespace(disbursed_amount=100000), SimpleNamespace(disbursed_amount=125000)]
        with patch.object(module, 'frappe', mock):
            getattr(module, function_name)(doc, 'onload')
        mock.get_all.assert_called_once_with('Loan Disbursement',
            filters={'against_loan': 'LOAN-A', 'docstatus': 1}, fields=['disbursed_amount'])
    assert doc.get_onload.return_value['total_principal'] == 225000
    assert doc.get_onload.return_value['pending_principal'] == 220500
    doc.db_set.assert_not_called()
    doc.save.assert_not_called()


def test_funding_display_preserves_other_loans_and_unsaved_states():
    from dcr.api import loan_readback
    for values in (
        {'docstatus': 0, 'original_financed_principal': 225000, 'home_build_request': 'HBR-A'},
        {'docstatus': 2, 'original_financed_principal': 225000, 'home_build_request': 'HBR-A'},
        {'docstatus': 1, 'home_build_request': 'HBR-A'},
        {'docstatus': 1, 'original_financed_principal': 225000},
    ):
        doc = MagicMock()
        doc.get.side_effect = values.get
        with patch.object(loan_readback, 'frappe') as frappe:
            loan_readback.show_posted_funding(doc)
        frappe.get_all.assert_not_called()
        doc.set_onload.assert_not_called()


def test_pending_principal_failure_does_not_return_original_funding_as_balance():
    import pytest
    with patch.object(payments, 'frappe') as frappe:
        frappe.db.exists.return_value = True
        with patch.object(payments, 'pending_principal', side_effect=ValueError('native read failed')):
            with pytest.raises(ValueError, match='native read failed'):
                payments.payment_summary({'name': 'LOAN-A', 'disbursed_amount': 225000}, 'DEALER-A')
