"""Verify saved hosted trial evidence without accessing or changing a server."""

import json
import sys
from datetime import date, timedelta
from decimal import Decimal


def money(value):
    return Decimal(str(value or 0))


def verify(proof):
    loan = proof['loan']
    rows = proof['rows']
    assert len(rows) == 14, 'Expected twelve IO receipts and payments 13–14'
    assert len({r['receipt']['name'] for r in rows}) == 14, 'Duplicate receipt'
    opening = Decimal('225000')
    io_interest = Decimal(0)
    for number, row in enumerate(rows, 1):
        receipt = row['receipt']
        days = (date.fromisoformat(row['payment_date']) - date.fromisoformat(row['period_start'])).days
        expected_interest = (opening * Decimal('.12') * days / 360).quantize(Decimal('.01'))
        expected_principal = Decimal(0) if number <= 12 else Decimal('2250')
        expected_total = expected_interest + expected_principal
        assert row['payment'] == number
        assert receipt['against_loan'] == loan and receipt['docstatus'] == 1
        assert receipt['value_date'][:10] == row['payment_date']
        assert money(receipt['amount_paid']) == expected_total
        assert money(receipt['total_interest_paid']) == expected_interest
        assert money(receipt['principal_amount_paid']) == expected_principal
        for key in ('total_penalty_paid', 'total_charges_paid', 'excess_amount'):
            assert money(receipt.get(key)) == 0, key
        accrual = row['accrual']
        assert len(accrual) == days
        expected_dates = {str(date.fromisoformat(row['period_start']) + timedelta(days=i)) for i in range(days)}
        assert {a['posting_date'][:10] for a in accrual} == expected_dates
        assert sum((money(a['interest_amount']) for a in accrual), Decimal(0)) == expected_interest
        assert sum((money(d['paid_amount']) for d in row['demands']), Decimal(0)) == expected_total
        assert all(money(d['outstanding_amount']) == 0 for d in row['demands'])
        entries = row['gl']
        assert sum((money(e['debit']) for e in entries), Decimal(0)) == expected_total
        assert sum((money(e['credit']) for e in entries), Decimal(0)) == expected_total
        assert all(e['against_voucher'] == loan for e in entries)
        opening -= expected_principal
        assert money(row['loan']['loan_amount']) - money(row['loan']['total_principal_paid']) == opening
        if number <= 12:
            io_interest += expected_interest
    assert io_interest == Decimal('27375')
    assert opening == Decimal('220500')
    ledger = proof['ledger']['rows']
    assert len({e['name'] for e in ledger}) == len(ledger)
    accounts = {}
    vouchers = {}
    for entry in ledger:
        balance = money(entry['debit']) - money(entry['credit'])
        accounts[entry['account']] = accounts.get(entry['account'], Decimal(0)) + balance
        key = (entry['voucher_type'], entry['voucher_no'])
        vouchers[key] = vouchers.get(key, Decimal(0)) + balance
    assert all(balance == 0 for balance in vouchers.values()), 'Incomplete/unbalanced voucher'
    assert sum(accounts.values(), Decimal(0)) == 0
    assert accounts['10202 - Loans Receivable - DCR'] == opening
    assert accounts['10101 - Chase Checking 9016 (Trust) - DCR'] == Decimal('36426.75')
    for account in ('Accrued Flooring Interest - DCR', 'Flooring Interest Receivable - DCR',
                    'Funding Clearing - DCR', 'DCR Fee Receivable - DCR'):
        assert accounts[account] == 0, account
    return dict(receipts=len(rows), io_interest=str(io_interest), remaining_principal=str(opening),
                ledger_rows=len(ledger), balanced_vouchers=len(vouchers))


if __name__ == '__main__':
    print(json.dumps(verify(json.loads(open(sys.argv[1]).read())), indent=2))
