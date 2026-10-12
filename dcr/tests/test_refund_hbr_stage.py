"""Refund hooks must reflect the loan state after the native controller runs."""
import importlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.parametrize('event', ['on_submit', 'on_cancel'])
@pytest.mark.parametrize('received', [False, True])
def test_refund_event_updates_request_from_current_loan_state(event, received):
    from dcr import hooks
    from dcr.api import hbr_stage

    payload = dict(loan='LOAN-DEMO', modified='2026-10-11 22:10:00', docstatus=1 if event == 'on_submit' else 2)
    refund = SimpleNamespace(doctype='Loan Refund', name='REFUND-DEMO', get=payload.get)
    request = dict(name='HBR-DEMO', customer='DEALER-DEMO', financing_type='Floored',
                   docstatus=1, modified='2026-10-11 22:00:00',
                   custom_loan_stage='Funded', custom_order_stage='Delivered' if received else 'Ordered')
    target = hooks.doc_events['Loan Refund'][event]
    module, _, method = target.rpartition('.')

    with patch.object(hbr_stage, 'frappe') as frappe, \
            patch.object(hbr_stage, '_has_column', return_value=True), \
            patch.object(hbr_stage, '_latest_loan_status', return_value='Closed'), \
            patch.object(hbr_stage, '_latest_loan_application_status', return_value='Signed'), \
            patch.object(hbr_stage, '_has_submitted_purchase_order', return_value=True), \
            patch.object(hbr_stage, '_has_submitted_purchase_receipt', return_value=received), \
            patch('dcr.api.status_notices.record_transition'):
        frappe.db.get_value.side_effect = lambda doctype, *args, **kwargs: (
            'HBR-DEMO' if doctype == 'Loan' else request)
        getattr(importlib.import_module(module), method)(refund, event)
        frappe.db.get_value.assert_any_call('Loan', 'LOAN-DEMO', 'home_build_request')
        expected = {'custom_loan_stage': 'Closed'}
        if received:
            expected['custom_order_stage'] = 'Closed'
        frappe.db.set_value.assert_called_once_with('Home Build Request', 'HBR-DEMO',
            expected, update_modified=False)


def test_refund_without_loan_does_not_update_a_request():
    from dcr.api import hbr_stage

    refund = SimpleNamespace(doctype='Loan Refund', name='REFUND-DEMO', get=lambda key: None)
    with patch.object(hbr_stage, 'frappe') as frappe:
        hbr_stage.sync_from_doc(refund, 'on_submit')
        frappe.db.set_value.assert_not_called()
