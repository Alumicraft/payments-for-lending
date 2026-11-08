from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dcr.api import payoff


def funded_loan(**values):
    doc = MagicMock(docstatus=1, status='Disbursed', disbursement_date='2026-11-01')
    doc.get.side_effect = lambda key: values.get(key, getattr(doc, key, None))
    for key, value in values.items():
        setattr(doc, key, value)
    return doc


def test_quote_uses_native_closure_amounts_and_read_permission_without_writes():
    loan = funded_loan()
    amounts = dict(payable_principal_amount=218250, interest_amount=3307.50,
                   penalty_amount=25, total_charges_payable=50, payable_amount=221632.50)
    with patch.object(payoff.frappe, 'get_doc', return_value=loan), \
            patch.object(payoff.frappe, 'get_all', return_value=[]), \
            patch.object(payoff, 'calculate_amounts', return_value=amounts) as calculate:
        result = payoff.flooring_payoff_quote('LOAN', '2028-01-15')
    assert result == dict(available=True, date='2028-01-15', principal=218250,
                         interest=3307.50, penalty=25, charges=50, total=221632.50)
    loan.check_permission.assert_called_once_with('read')
    calculate.assert_called_once_with('LOAN', '2028-01-15', payment_type='Loan Closure')
    loan.save.assert_not_called()
    loan.db_set.assert_not_called()


def test_closed_or_unfunded_loan_does_not_get_a_new_interest_quote():
    for values in [dict(status='Closed'), dict(docstatus=0), dict(status='Sanctioned')]:
        with patch.object(payoff.frappe, 'get_doc', return_value=funded_loan(**values)), \
                patch.object(payoff, 'calculate_amounts') as calculate:
            assert payoff.flooring_payoff_quote('LOAN')['available'] is False
            calculate.assert_not_called()


def test_quote_rejects_dates_before_funding_or_a_later_posted_principal_event():
    with patch.object(payoff.frappe, 'get_doc', return_value=funded_loan()), \
            patch.object(payoff.frappe, 'get_all', return_value=[
                SimpleNamespace(value_date='2028-01-01')]), \
            patch.object(payoff, 'calculate_amounts') as calculate:
        assert payoff.flooring_payoff_quote('LOAN', '2026-10-31')['available'] is False
        assert payoff.flooring_payoff_quote('LOAN', '2027-12-31')['available'] is False
        calculate.assert_not_called()


def test_payoff_email_passes_the_selected_date_to_the_actual_print_document():
    from dcr.api import docusign
    loan = SimpleNamespace(applicant='DEALER')
    customer = SimpleNamespace(email_id='send2tristan@gmail.com', customer_name='Demo Dealer')
    with patch.object(docusign, 'require_staff'), \
            patch.object(docusign.frappe, 'get_doc', side_effect=[loan, customer]), \
            patch.object(payoff, 'flooring_payoff_quote', return_value=dict(
                available=True, date='2028-01-15')) as quote, \
            patch.object(docusign.frappe, 'get_print', return_value=b'%PDF') as render, \
            patch('dcr.api.dcr_email.send_payoff_letter') as send:
        assert docusign.send_payoff_letter('LOAN', quote_date='2028-01-15')['success'] is True
    quote.assert_called_once_with('LOAN', '2028-01-15')
    assert loan.payoff_quote_date == '2028-01-15'
    assert render.call_args.kwargs['doc'] is loan
    send.assert_called_once()


def test_invalid_payoff_quote_cannot_be_rendered_or_emailed():
    from dcr.api import docusign
    with patch.object(docusign, 'require_staff'), \
            patch.object(docusign.frappe, 'get_doc', side_effect=[
                SimpleNamespace(applicant='DEALER'), SimpleNamespace(email_id='send2tristan@gmail.com')]), \
            patch.object(payoff, 'flooring_payoff_quote', return_value=dict(
                available=False, reason='Review the payoff date.')), \
            patch.object(docusign.frappe, 'get_print') as render, \
            patch('dcr.api.dcr_email.send_payoff_letter') as send:
        import pytest
        with pytest.raises(Exception):
            docusign.send_payoff_letter('LOAN', quote_date='2026-01-01')
    render.assert_not_called()
    send.assert_not_called()
