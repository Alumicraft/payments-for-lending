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


def fee_invoice_row(**values):
    return Doc(currency="USD", conversion_rate=1, **values)


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
    disbursement = Doc(name='DISB',against_loan='LOAN',disbursed_amount=225000,
                      disbursement_date='2026-01-01',repayment_start_date='2026-02-01',
                      loan_disbursement_charges=[Doc(charge='FEE',amount=5000,
                          treatment_of_charge='Billed Separately')])
    with patch.object(rules,'frappe') as f:
        def fail(message, *args, **kwargs):
            raise ValueError(message)
        f.throw.side_effect = fail
        f.get_doc.side_effect = lambda doctype,name: {'Purchase Invoice':invoice,'Home Build Request':request,
                                                    'Loan Application':application,'Loan':loan}[doctype]
        f.db.get_value.side_effect = lambda doctype,*args,**kwargs: ('Actual/360' if args[-1] == 'interest_day_count_convention' else 'USD') if doctype == 'Company' else Doc(name='SIG',signed_attachment='/private/files/demo.pdf')
        f.db.exists.return_value = True
        f.get_all.return_value = []
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


def test_funding_freezes_reviewed_principal_and_never_overwrites_it(deal):
    app, _, loan, disbursement, f = deal
    rules.apply_application_invoice(app)
    rules.validate_invoice_funding(disbursement)
    f.db.set_value.assert_called_once_with('Loan', 'LOAN', 'original_financed_principal', 225000.0)
    loan.set('original_financed_principal', 225000)
    f.db.set_value.reset_mock()
    rules.validate_invoice_funding(disbursement)
    f.db.set_value.assert_not_called()
    loan.set('original_financed_principal', 220000)
    with pytest.raises(ValueError, match='already fixed'):
        rules.validate_invoice_funding(disbursement)
    f.db.set_value.assert_not_called()


def test_failed_date_admission_cannot_freeze_a_loan_basis(deal):
    app, _, _, disbursement, f = deal
    rules.apply_application_invoice(app)
    disbursement.set('disbursement_date', '2026-01-20')
    with pytest.raises(ValueError, match='Funding date must equal'):
        rules.validate_invoice_funding(disbursement)
    f.db.set_value.assert_not_called()


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


def test_daily_frequency_cannot_fund_a_monthly_floorplan_contract(deal):
    app,_,_,disbursement,_ = deal
    rules.apply_application_invoice(app)
    disbursement.set('repayment_frequency','Daily')
    with pytest.raises(ValueError,match='requires monthly'):
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


def test_full_funding_requires_actual_financed_fee_charges(deal):
    app, _, _, disb, _ = deal
    rules.apply_application_invoice(app)
    disb['loan_disbursement_charges'] = []
    with pytest.raises(ValueError, match='financed fees'):
        rules.validate_invoice_funding(disb)


@pytest.mark.parametrize('amount,treatment', [(5001, 'Billed Separately'),
                                             (5000, 'Add to first repayment'),
                                             (-1, 'Billed Separately')])
def test_financed_charges_cannot_exceed_basis_or_be_collected_twice(deal, amount, treatment):
    app, _, _, disb, _ = deal
    rules.apply_application_invoice(app)
    disb['loan_disbursement_charges'] = [Doc(amount=amount,treatment_of_charge=treatment)]
    with pytest.raises(ValueError, match='financed|negative'):
        rules.validate_invoice_funding(disb)


def test_fees_already_on_factory_invoice_are_not_charged_again(deal):
    app, invoice, _, disb, _ = deal
    invoice['grand_total'] = 225000
    app['financed_dcr_fees'] = 0
    rules.apply_application_invoice(app)
    with pytest.raises(ValueError, match='financed fees'):
        rules.validate_invoice_funding(disb)


def test_partial_funding_can_allocate_fee_at_final_tranche(deal):
    app, _, _, disb, f = deal
    rules.apply_application_invoice(app)
    disb['disbursed_amount'] = 100000
    disb['loan_disbursement_charges'] = []
    rules.validate_invoice_funding(disb)
    disb['disbursed_amount'] = 125000
    disb['loan_disbursement_charges'] = [Doc(amount=5000,treatment_of_charge='Billed Separately')]
    f.get_all.side_effect = lambda doctype, **kwargs: (
        [Doc(name='PRIOR',disbursed_amount=100000)] if doctype == 'Loan Disbursement' else [])
    rules.validate_invoice_funding(disb)


def test_later_tranche_does_not_repeat_fees_already_invoiced(deal):
    app, _, _, disb, f = deal
    rules.apply_application_invoice(app)
    disb['disbursed_amount'] = 125000
    f.get_all.side_effect = lambda doctype, **kwargs: (
        [Doc(name='PRIOR',disbursed_amount=100000)] if doctype == 'Loan Disbursement'
        else [fee_invoice_row(grand_total=5000)])
    with pytest.raises(ValueError, match='financed fees'):
        rules.validate_invoice_funding(disb)
    disb['loan_disbursement_charges'] = []
    rules.validate_invoice_funding(disb)


@pytest.mark.parametrize('posted', [[], [fee_invoice_row(grand_total=5300, debit_to='FEE-AR')]])
def test_native_posting_must_invoice_the_exact_financed_fee(deal, posted):
    _, _, _, disb, f = deal
    f.get_all.side_effect = lambda doctype, **kwargs: posted if doctype=='Sales Invoice' else []
    with pytest.raises(ValueError, match='Posted fee invoice total'):
        rules.validate_posted_financed_fees(disb)


def test_native_fee_invoice_must_use_selected_receivable(deal):
    _, _, _, disb, f = deal
    disb['loan_disbursement_charges'][0]['account'] = 'FEE-AR'
    invoices = [fee_invoice_row(grand_total=5000, debit_to='OTHER-AR')]
    f.get_all.side_effect = lambda doctype, **kwargs: invoices if doctype=='Sales Invoice' else []
    with pytest.raises(ValueError, match='receivable account differs'):
        rules.validate_posted_financed_fees(disb)
    invoices[0]['debit_to'] = 'FEE-AR'
    rules.validate_posted_financed_fees(disb)


def test_native_fee_invoice_cannot_silently_ignore_a_second_receivable(deal):
    _, _, _, disb, f = deal
    disb['loan_disbursement_charges'] = [
        Doc(amount=2500, account='FEE-AR',treatment_of_charge='Billed Separately'),
        Doc(amount=2500, account='OTHER-AR',treatment_of_charge='Billed Separately')]
    f.get_all.side_effect = lambda doctype, **kwargs: (
        [fee_invoice_row(grand_total=5000, debit_to='FEE-AR')] if doctype=='Sales Invoice' else [])
    with pytest.raises(ValueError, match='receivable account differs'):
        rules.validate_posted_financed_fees(disb)


def test_native_fee_checks_are_scoped_to_home_financing(deal):
    _, _, loan, disb, f = deal
    loan['home_build_request'] = None
    rules.validate_posted_financed_fees(disb)
    f.get_all.assert_not_called()


def test_fee_checks_lock_the_loan_and_exclude_cancelled_or_current_disbursements(deal):
    app, _, _, disb, f = deal
    rules.apply_application_invoice(app)
    rules.validate_invoice_funding(disb)
    f.db.get_value.assert_any_call('Loan','LOAN','name',for_update=True)
    prior_query = next(call for call in f.get_all.call_args_list if call.args[0]=='Loan Disbursement')
    assert prior_query.kwargs['filters']=={
        'against_loan':'LOAN','docstatus':1,'name':['!=','DISB']}


def test_posted_fee_check_runs_before_stage_sync():
    from dcr import hooks
    assert hooks.doc_events['Loan Disbursement']['on_submit']==[
        'dcr.api.financing_basis.validate_posted_financed_fees',
        'dcr.api.hbr_stage.sync_from_doc']


def test_signed_financed_fees_can_include_native_exclusive_tax(deal):
    app, _, loan, disb, f = deal
    app['financed_dcr_fees'] = 5300
    rules.apply_application_invoice(app)
    loan['loan_amount'] = disb['disbursed_amount'] = 225300
    rules.validate_invoice_funding(disb)  # Fee item 5000 plus native tax 300
    f.get_all.side_effect = lambda doctype, **kwargs: (
        [fee_invoice_row(grand_total=5300, debit_to='FEE-AR')] if doctype == 'Sales Invoice' else [])
    rules.validate_posted_financed_fees(disb)


def test_full_funding_rejects_fee_shortfall_after_native_invoice_calculation(deal):
    app, _, _, disb, f = deal
    rules.apply_application_invoice(app)
    disb['loan_disbursement_charges'][0]['amount'] = 4500
    rules.validate_invoice_funding(disb)  # Tax calculation occurs later
    f.get_all.side_effect = lambda doctype, **kwargs: (
        [fee_invoice_row(grand_total=4500)] if doctype == 'Sales Invoice' else [])
    with pytest.raises(ValueError, match='Posted fee invoice total'):
        rules.validate_posted_financed_fees(disb)


def test_only_home_disbursement_fee_invoices_disable_separate_rounding(deal):
    _, _, _, _, f = deal
    fee_invoice = Doc(loan='LOAN',loan_disbursement='DISB',disable_rounded_total=0)
    rules.prepare_financed_charge_invoice(fee_invoice)
    assert fee_invoice.disable_rounded_total == 1
    ordinary = Doc(loan=None,loan_disbursement=None,disable_rounded_total=0)
    rules.prepare_financed_charge_invoice(ordinary)
    assert ordinary.disable_rounded_total == 0
    f.db.get_value.side_effect = None
    f.db.get_value.return_value = None
    other_loan = Doc(loan='OTHER',loan_disbursement='OTHER-DISB',disable_rounded_total=0)
    rules.prepare_financed_charge_invoice(other_loan)
    assert other_loan.disable_rounded_total == 0


def test_home_funding_requires_loan_accounting_enabled(deal):
    app, _, _, disb, f = deal
    rules.apply_application_invoice(app)
    original = f.db.get_value.side_effect
    f.db.get_value.side_effect = lambda doctype, *args, **kwargs: (
        0 if doctype == 'Company' and args[-1] == 'enable_loan_accounting'
        else original(doctype, *args, **kwargs))
    with pytest.raises(ValueError, match='Enable loan accounting'):
        rules.validate_invoice_funding(disb)
    f.db.set_value.assert_not_called()


@pytest.mark.parametrize('currency,rate', [('CAD', 1), ('USD', 1.1)])
def test_fee_posting_uses_the_signed_currency(deal, currency, rate):
    _, _, _, disb, f = deal
    invoice = fee_invoice_row(grand_total=5000)
    invoice.update(currency=currency, conversion_rate=rate)
    f.get_all.side_effect = lambda doctype, **kwargs: [invoice] if doctype=='Sales Invoice' else []
    with pytest.raises(ValueError, match='reviewed company currency'):
        rules.validate_posted_financed_fees(disb)
