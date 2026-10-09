from unittest.mock import patch
from dcr.api.lending import _apply_loan_calculation_values, _loan_calculation_values, get_dated_loan_preview
from dcr.tests.test_lending_guards import _Doc


def test_first_dated_payment_uses_actual_days_and_full_continuing_term():
    result = _loan_calculation_values(225000,12,36,
        interest_start_date='2026-01-01',first_payment_date='2026-02-01')
    assert result['monthly_repayment_amount'] == 2325  # 31 days / 360
    assert result['repayment_periods'] == 112  # No month-36 balloon
    assert result['total_interest_payable'] > 2325 * 36  # Full term, not a 36-month subtotal


def test_saved_loan_forecast_uses_visible_principal_and_real_first_period():
    doc = _Doc(doctype='Loan',docstatus=0,loan_amount=225000,qualifying_amount=100000,
               rate_of_interest=12,repayment_periods=12,posting_date='2026-01-20',
               repayment_start_date='2026-02-01')
    _apply_loan_calculation_values(doc)
    assert doc.monthly_repayment_amount == 400  # 100,000, twelve days
    assert doc.repayment_periods == 112


def test_linked_loan_preview_uses_invoice_date_not_later_loan_creation_date():
    with patch('dcr.api.lending.require_staff'),patch('dcr.api.lending.frappe') as f:
        f.db.get_value.return_value = '2026-01-01'
        result = get_dated_loan_preview('Loan',225000,12,36,
            interest_start_date='2026-01-20',first_payment_date='2026-02-01',loan_application='APP')
    assert result['monthly_repayment_amount'] == 2325


def test_undated_preview_has_no_invented_payment_but_retains_equity():
    result = _loan_calculation_values(225000,12,36,250000)
    assert result['monthly_repayment_amount'] is None
    assert result['total_interest_payable'] is None
    assert result['custom_projected_equity'] == 25000


def test_already_submitted_loan_totals_are_not_reforecast_on_unrelated_save():
    doc = _Doc(doctype='Loan',docstatus=1,monthly_repayment_amount=987,total_payment=123456)
    _apply_loan_calculation_values(doc)
    assert doc.monthly_repayment_amount == 987
    assert doc.total_payment == 123456
