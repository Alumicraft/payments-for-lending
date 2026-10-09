"""Final invoice, signature revision and funding admission business cases."""
from unittest.mock import MagicMock, patch
import pytest

from dcr.api import financing_basis as rules


class Doc(dict):
    def __getattr__(self, key):
        return self.get(key)

    def set(self,key,value):
        self[key] = value

    def check_permission(self,permission):
        return None


@pytest.fixture
def deal():
    application = Doc(name='APP',company='DCR',applicant='DEALER',home_build_request='HBR',
                      loan_amount=220000,financed_invoice='PI',financed_dcr_fees=5000,
                      rate_of_interest=12,monthly_insurance_amount=100)
    application.set('first_payment_date','2026-02-01')
    invoice = Doc(name='PI',docstatus=1,company='DCR',currency='USD',supplier='FACTORY',
                  home_build_request='HBR',grand_total=220000,bill_date='2026-01-01',
                  posting_date='2026-01-20')
    request = Doc(customer='DEALER',factory='FACTORY')
    loan = Doc(name='LOAN',loan_application='APP',home_build_request='HBR',applicant='DEALER',
               company='DCR',loan_amount=225000,rate_of_interest=12)
    disbursement = Doc(against_loan='LOAN',disbursement_date='2026-01-01',repayment_start_date='2026-02-01')
    with patch.object(rules,'frappe') as f:
        def fail(message, *args, **kwargs):
            raise ValueError(message)
        f.throw.side_effect = fail
        f.get_doc.side_effect = lambda doctype,name: {'Purchase Invoice':invoice,'Home Build Request':request,
                                                    'Loan Application':application,'Loan':loan}[doctype]
        f.db.get_value.side_effect = lambda doctype,*args,**kwargs: ('Actual/360' if args[-1] == 'interest_day_count_convention' else 'USD') if doctype == 'Company' else Doc(name='SIG',signed_attachment='/private/files/demo.pdf')
        f.db.exists.return_value = True
        yield application,invoice,loan,disbursement,f


def test_canonical_invoice_total_plus_only_additional_fees_and_supplier_date(deal):
    app,invoice,_,_,_ = deal
    rules.apply_application_invoice(app)
    assert app.loan_amount == app.requested_advance_amount == 225000
    assert app.financed_invoice_date == '2026-01-01'  # Supplier date, not later posting date
    # Dict document setters deliberately use normal Document.set semantics.
    app.set('financed_dcr_fees',0)
    rules.apply_application_invoice(app)
    assert app.loan_amount == 220000  # No second addition of fees already on invoice


@pytest.mark.parametrize('changes', [dict(docstatus=0),dict(is_return=1),dict(company='OTHER'),
                                     dict(currency='EUR'),dict(home_build_request='OTHER'),
                                     dict(supplier='OTHER')])
def test_wrong_invoice_cannot_define_financed_principal(deal,changes):
    app,invoice,_,_,_ = deal
    invoice.update(changes)
    with pytest.raises(ValueError): rules.financial_snapshot(app,require_invoice=True)


def test_quote_review_cannot_authorize_final_invoice_funding(deal):
    app,_,_,disbursement,_ = deal
    app.set('financed_invoice',None)
    assert rules.financial_snapshot(app)['source'] == 'quote'
    with pytest.raises(ValueError,match='final Funding Invoice'):
        rules.validate_invoice_funding(disbursement)


def test_funding_requires_matching_amount_date_and_signed_snapshot(deal):
    app,_,_,disbursement,f = deal
    rules.apply_application_invoice(app)
    rules.validate_invoice_funding(disbursement)
    query = next(call for call in f.db.get_value.call_args_list if call.args[0] == 'Signature Request')
    assert query.args[1]['financial_basis_hash'] == rules.snapshot_hash(rules.financial_snapshot(app))
    assert query.args[1]['status'] == 'Signed'
    disbursement.set('disbursement_date','2026-01-20')
    with pytest.raises(ValueError,match='Funding date must equal'):
        rules.validate_invoice_funding(disbursement)


def test_changed_invoice_does_not_use_previously_signed_principal(deal):
    app,invoice,_,disbursement,f = deal
    rules.apply_application_invoice(app)
    old = rules.snapshot_hash(rules.financial_snapshot(app))
    invoice.set('grand_total',230000)
    assert old != rules.snapshot_hash(rules.financial_snapshot(app))
    with pytest.raises(ValueError,match='principal must match'):
        rules.validate_invoice_funding(disbursement)
    rules.apply_application_invoice(app)
    deal[2].set('loan_amount',235000)
    f.db.get_value.side_effect = lambda doctype,*args,**kwargs: ('Actual/360' if args[-1] == 'interest_day_count_convention' else 'USD') if doctype == 'Company' else None
    with pytest.raises(ValueError,match='dealer must sign'):
        rules.validate_invoice_funding(disbursement)


def test_unavailable_signed_file_blocks_funding(deal):
    app,_,_,disbursement,f = deal
    rules.apply_application_invoice(app)
    f.db.exists.return_value = False
    with pytest.raises(ValueError,match='file is unavailable'):
        rules.validate_invoice_funding(disbursement)


def test_bill_date_falls_back_to_invoice_posting_date(deal):
    app,invoice,_,_,_ = deal
    invoice.set('bill_date',None)
    assert rules.financial_snapshot(app)['invoice_date'] == '2026-01-20'


def test_rounded_invoice_total_is_the_financed_payable_amount(deal):
    app,invoice,_,_,_ = deal
    invoice.update(grand_total=220000.43,rounded_total=220000)
    assert rules.financial_snapshot(app)['principal'] == '225000.00'
    invoice.set('disable_rounded_total',1)
    assert rules.financial_snapshot(app)['principal'] == '225000.43'


def test_cross_request_loan_cannot_use_another_deal_packet(deal):
    app,_,loan,disbursement,_ = deal
    rules.apply_application_invoice(app)
    loan.set('home_build_request','OTHER-HBR')
    with pytest.raises(ValueError,match='Home Build Request'):
        rules.validate_invoice_funding(disbursement)


def test_packet_cannot_describe_a_payment_before_interest_starts(deal):
    app,_,_,_,_ = deal
    app.set('first_payment_date','2025-12-31')
    with pytest.raises(ValueError,match='cannot precede'):
        rules.financial_snapshot(app)


@pytest.mark.parametrize('changes', [dict(rate_of_interest=15),dict(qualifying_amount=200000)])
def test_loan_cannot_fund_different_terms_from_reviewed_application(deal,changes):
    app,_,loan,disbursement,_ = deal
    rules.apply_application_invoice(app)
    loan.update(changes)
    with pytest.raises(ValueError): rules.validate_invoice_funding(disbursement)


def test_rates_are_not_rounded_like_currency_when_matching_signed_terms(deal):
    app,_,loan,disbursement,_ = deal
    app.set('rate_of_interest',12.345)
    loan.set('rate_of_interest',12.346)
    rules.apply_application_invoice(app)
    with pytest.raises(ValueError,match='interest rate must match'):
        rules.validate_invoice_funding(disbursement)


def test_actual365_company_cannot_fund_actual360_packet(deal):
    app,_,_,disbursement,f = deal
    rules.apply_application_invoice(app)
    previous = f.db.get_value.side_effect
    f.db.get_value.side_effect = lambda doctype,*args,**kwargs: 'Actual/365' if doctype == 'Company' and args[-1] == 'interest_day_count_convention' else previous(doctype,*args,**kwargs)
    with pytest.raises(ValueError,match='must be Actual/360'):
        rules.validate_invoice_funding(disbursement)


@pytest.mark.parametrize('changes', [dict(interest_only_periods=6),dict(monthly_principal_percent=2)])
def test_product_curtailment_must_match_owner_approved_rules(deal,changes):
    app,_,_,disbursement,_ = deal
    rules.apply_application_invoice(app)
    terms = dict(annual_rate=12,interest_only_periods=12,monthly_principal_percent=1,
                 day_count='Actual/360',schedule_type='Interest Only Then Percent Principal')
    terms.update(changes)
    with patch.object(rules,'product_terms',return_value=terms):
        with pytest.raises(ValueError,match='requires 12 interest-only'):
            rules.validate_invoice_funding(disbursement)


def test_metadata_prevents_duplicate_signature_and_quote_overwrite():
    with patch.object(rules,'frappe') as f:
        f.get_meta.return_value.has_field.return_value = True
        f.db.exists.return_value = None
        rules.ensure_financing_fields()
        properties = [call.args[0] for call in f.get_doc.call_args_list]
    assert {(row['field_name'],row['property'],row['value']) for row in properties} == {
        ('signed_packet','no_copy','1'),('status','no_copy','1'),('loan_amount','fetch_from','')}


@pytest.mark.parametrize('field,value', [('grand_total','NaN'),('grand_total','Infinity')])
def test_non_finite_invoice_amount_fails(deal,field,value):
    app,invoice,_,_,_ = deal
    invoice.set(field,value)
    with pytest.raises(ValueError): rules.financial_snapshot(app)
