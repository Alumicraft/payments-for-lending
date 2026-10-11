from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
import pytest

from dcr.api import lending


class Doc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        setattr(self, key, value)


def test_application_defaults_read_dates_and_preserve_first_payment():
    application = dict(docstatus=1, applicant='DEALER', loan_product='Standard',
                       loan_amount=225000, rate_of_interest=12, repayment_periods=112,
                       financed_invoice_date='2026-10-01', first_payment_date='2026-11-01')

    def get_value(doctype, name, fields, **kwargs):
        assert doctype == 'Loan Application'
        return Doc(**{field: application.get(field) for field in fields})

    terms = dict(schedule_type='Interest Only Then Percent Principal', annual_rate=12,
                 interest_only_periods=12, monthly_principal_percent=1)
    with patch.object(lending, 'frappe') as frappe, \
            patch.object(lending, 'require_staff'), \
            patch.object(lending, '_compute_deal_reference', return_value={}), \
            patch.object(lending, 'product_terms', return_value=terms):
        frappe.db.get_value.side_effect = get_value
        frappe.get_meta.return_value.has_field.return_value = True
        defaults = lending.get_loan_defaults_from_application('APPLICATION')

    assert defaults.get('repayment_start_date') == '2026-11-01'
    assert defaults['monthly_repayment_amount'] == 2325


@pytest.mark.parametrize('docstatus,action,expected', [
    (0, 'save', '2026-11-01'), (1, 'submit', '2026-11-01'),
    (1, 'update_after_submit', '2026-10-11'), (2, 'cancel', '2026-10-11'),
])
def test_save_aligns_new_loan_but_preserves_submitted_dates(docstatus, action, expected):
    loan = Doc(docstatus=docstatus, _action=action, home_build_request='HOME',
               loan_application='APPLICATION', applicant='DEALER', loan_product='Standard',
               repayment_start_date='2026-10-11')
    application = dict(docstatus=1, applicant='DEALER', loan_product='Standard',
                       financed_invoice='INVOICE', first_payment_date='2026-11-01')
    with patch.object(lending, 'frappe') as frappe:
        frappe.db.get_value.return_value = application
        lending.apply_application_repayment_date(loan)
    assert loan.repayment_start_date == expected


@pytest.mark.parametrize('change', [
    {'docstatus': 0}, {'financed_invoice': None}, {'first_payment_date': None},
    {'applicant': 'OTHER'}, {'loan_product': 'OTHER'},
])
def test_unrelated_or_unapproved_application_does_not_rewrite_date(change):
    loan = Doc(docstatus=0, home_build_request='HOME', loan_application='APPLICATION',
               applicant='DEALER', loan_product='Standard', repayment_start_date='2026-10-11')
    application = dict(docstatus=1, applicant='DEALER', loan_product='Standard',
                       financed_invoice='INVOICE', first_payment_date='2026-11-01')
    application.update(change)
    with patch.object(lending, 'frappe') as frappe:
        frappe.db.get_value.return_value = application
        lending.apply_application_repayment_date(loan)
    assert loan.repayment_start_date == '2026-10-11'


def test_mapper_keeps_native_accounts_and_permissions_then_applies_dates():
    loan = Doc(repayment_start_date='2026-10-11', monthly_repayment_amount=750,
               payment_account='NATIVE PAYMENT ACCOUNT')
    native = Mock(return_value=loan)
    module = SimpleNamespace(create_loan=native)
    defaults = {'repayment_start_date': '2026-11-01', 'monthly_repayment_amount': 2325}
    with patch.dict(sys.modules, {
            'lending.loan_management.doctype.loan_application.loan_application': module}), \
            patch.object(lending, 'get_loan_defaults_from_application', return_value=defaults), \
            patch.object(lending, 'frappe') as frappe:
        frappe.get_meta.return_value.has_field.return_value = True
        result = lending.create_loan_from_application('APPLICATION')
        native.assert_called_once_with('APPLICATION', None)
        assert result is loan
        assert result.repayment_start_date == '2026-11-01'
        assert result.monthly_repayment_amount == 2325
        assert result.payment_account == 'NATIVE PAYMENT ACCOUNT'
        native.side_effect = PermissionError('Loan create denied')
        with pytest.raises(PermissionError, match='Loan create denied'):
            lending.create_loan_from_application('APPLICATION')
