"""Verify the single-row CSV exported by extra_principal_readback.sql."""
import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('.01'))


def verify(path, phase):
    csv.field_size_limit(8 * 1024 * 1024)
    with path.open(newline='', encoding='utf-8-sig') as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 1, 'Expected one scoped readback row'
    data = {key: json.loads(value) if value else [] for key, value in rows[0].items()
            if key != 'readback_id'}
    loan, = data['loan']
    assert loan['name'] == 'ACC-LOAN-2026-00026'
    assert money(loan['original_financed_principal']) == 225000
    receipts = [r for r in data['receipts'] if r['docstatus'] == 1]
    extra = [r for r in receipts if r['name'] == 'LM-REP-0039']
    expected_principal = {'baseline': 220500, 'extra': 215500, 'monthly': 213250,
                          'closed': 0, 'reversed': 220500, 'recovered': 220500}[phase]
    actual_principal = Decimal(225000) - sum(money(r['principal_amount_paid']) for r in receipts)
    assert actual_principal == expected_principal, (actual_principal, expected_principal)
    pending = money(loan['total_payment']) - money(loan['total_interest_payable']) - money(loan['total_principal_paid'])
    pending += money(loan['debit_adjustment_amount']) - money(loan['credit_adjustment_amount'])
    assert pending == expected_principal, ('native pending principal', pending)
    if phase in ('extra', 'monthly', 'closed'):
        receipt, = extra
        assert receipt['is_term_loan'] == 1
        assert money(receipt['amount_paid']) == money(receipt['principal_amount_paid']) == 5000
        assert money(receipt['total_interest_paid']) == 0
        restructure, = [r for r in data['restructures']
                        if r['loan_repayment'] == receipt['name'] and r['docstatus'] == 1]
        schedule, = [s for s in data['schedules'] if s['loan_restructure'] == restructure['name']]
        row, = [r for r in data['installments'] if r['parent'] == schedule['name'] and str(r['payment_date'])[:10] == '2028-02-01']
        assert money(row['principal_amount']) == 2250
        assert money(row['interest_amount']) == Decimal('2250.17')
        assert money(row['total_payment']) == Decimal('4500.17')
        if phase == 'extra':
            assert row['demand_generated'] == 0
    else:
        assert not extra
        assert len(receipts) == 14
        if phase in ('reversed', 'recovered'):
            cancelled, = [r for r in data['receipts'] if r['name'] == 'LM-REP-0039']
            assert cancelled['docstatus'] == 2
            assert any(r['docstatus'] == 2 and r['repayment_type'] == 'Normal Repayment'
                       and str(r['value_date'])[:10] == '2028-02-01' for r in data['receipts'])
    if phase in ('monthly', 'closed'):
        monthly, = [r for r in receipts if r['repayment_type'] == 'Normal Repayment'
                    and str(r['value_date'])[:10] == '2028-02-01']
        assert money(monthly['principal_amount_paid']) == 2250
        assert money(monthly['total_interest_paid']) == Decimal('2250.17')
        assert money(monthly['amount_paid']) == Decimal('4500.17')
    if phase == 'closed':
        assert loan['status'] == 'Closed'
        closure, = [r for r in receipts if r['repayment_type'] == 'Loan Closure']
        assert money(closure['principal_amount_paid']) == 213250
        assert money(closure['total_interest_paid']) == Decimal('995.17')
        assert money(closure['amount_paid']) == Decimal('214245.17')
    else:
        assert loan['status'] in ('Disbursed', 'Active')
    active_gl = [r for r in data['gl'] if not r['is_cancelled']]
    vouchers, accounts = defaultdict(Decimal), defaultdict(Decimal)
    for row in active_gl:
        value = money(row['debit']) - money(row['credit'])
        vouchers[(row['voucher_type'], row['voucher_no'])] += value
        accounts[row['account']] += value
    assert vouchers and all(value == 0 for value in vouchers.values()), 'Unbalanced or missing vouchers'
    for account in ('10202 - Loans Receivable - DCR', '10101 - Chase Checking 9016 (Trust) - DCR',
                    '40102 - Flooring Interest Income - DCR', 'Accrued Flooring Interest - DCR',
                    'Flooring Interest Receivable - DCR', 'Funding Clearing - DCR', 'DCR Fee Receivable - DCR'):
        assert account in accounts, ('Required account is missing from the export', account)
    assert accounts['10202 - Loans Receivable - DCR'] == expected_principal
    cash = sum(money(r['amount_paid']) for r in receipts)
    interest_paid = sum(money(r['total_interest_paid']) for r in receipts)
    assert accounts['10101 - Chase Checking 9016 (Trust) - DCR'] == cash
    earned = sum(money(a['interest_amount']) for a in data['accruals']
                 if a['docstatus'] == 1 and a['interest_type'] == 'Normal Interest')
    demanded = sum(money(d['demand_amount']) for d in data['demands']
                   if d['docstatus'] == 1 and d['demand_subtype'] == 'Interest')
    if phase == 'recovered':
        assert earned == Decimal('32955.75'), 'Retain earned interest through January 14 only'
        assert not any(a['docstatus'] == 1 and str(a['posting_date'])[:10] >= '2028-01-15'
                       for a in data['accruals']), 'Future accruals still depend on the cancelled principal event'
        assert not any(d['docstatus'] == 1 and str(d['demand_date'])[:10] >= '2028-01-15'
                       for d in data['demands']), 'Future demands were not reversed'
        schedule, = [s for s in data['schedules'] if s['docstatus'] == 1 and s['status'] == 'Active']
        assert schedule['name'] == 'LN-RS-2026-00020'
        row, = [r for r in data['installments'] if r['parent'] == schedule['name']
                and str(r['payment_date'])[:10] == '2028-02-01']
        assert money(row['principal_amount']) == 2250
        assert money(row['interest_amount']) == Decimal('2278.50')
        assert money(row['total_payment']) == Decimal('4528.50')
        assert row['demand_generated'] == 0
    assert accounts['40102 - Flooring Interest Income - DCR'] == -earned
    assert accounts['Accrued Flooring Interest - DCR'] == earned - demanded
    assert accounts['Flooring Interest Receivable - DCR'] == demanded - interest_paid
    for account in ('Funding Clearing - DCR', 'DCR Fee Receivable - DCR'):
        assert accounts[account] == 0
    return dict(phase=phase, principal=str(actual_principal), receipts=len(receipts),
                cash=str(cash), earned_interest=str(earned), interest_collected=str(interest_paid),
                gl_rows=len(active_gl), balanced_vouchers=len(vouchers))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('phase', choices=('baseline', 'extra', 'monthly', 'closed', 'reversed', 'recovered'))
    args = parser.parse_args()
    print(json.dumps(verify(args.csv, args.phase), indent=2))
