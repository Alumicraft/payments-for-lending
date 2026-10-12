"""Reconcile native CSV exports without writing to Frappe or proposing adjustments."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def records(path):
    with Path(path).open(newline='') as source:
        return [{key.strip(): value for key, value in row.items() if key}
                for row in csv.DictReader(source)]


def identifier(row):
    return row['ID'].strip('"')


def day(value):
    return datetime.strptime(value[:10], '%m-%d-%Y').date()


def reconcile(gl, accruals, demands):
    posted = defaultdict(set)
    vouchers = defaultdict(list)
    for row in gl:
        if row.get('Voucher No'):
            posted[row['Voucher Type']].add(row['Voucher No'])
            vouchers[(row['Voucher Type'], row['Voucher No'])].append(row)
    for kind, exported in (('Loan Interest Accrual', accruals), ('Loan Demand', demands)):
        missing = posted[kind] - {identifier(row) for row in exported}
        if missing:
            raise ValueError(f'{kind} export is missing {len(missing)} posted vouchers')
    suspect = set()
    for (kind, name), rows in vouchers.items():
        if kind != 'Loan Interest Accrual':
            continue
        debit = sum(Decimal(row['Debit (USD)'] or '0') for row in rows)
        credit = sum(Decimal(row['Credit (USD)'] or '0') for row in rows)
        if len({row['Account'] for row in rows}) == 1 and debit == credit and debit > 0:
            suspect.add(name)
    accruals = [row for row in accruals if identifier(row) in posted['Loan Interest Accrual']]
    loans = {row['Loan'] for row in accruals if identifier(row) in suspect}
    result = {}
    for loan in sorted(loans):
        spans = defaultdict(list)
        rates = Counter()
        selected = [row for row in accruals if row['Loan'] == loan]
        for row in selected:
            first = day(row['Start Date'])
            if row['Is Term Loan'] != '1':
                first += timedelta(days=1)
            end = day(row['Posting Date (End Date)']) + timedelta(days=1)
            days = (end - first).days
            if days <= 0:
                raise ValueError(f'Invalid accrual period in {identifier(row)}')
            matches = []
            for basis in (360, 365):
                expected = (Decimal(row['Base Amount']) * Decimal(row['Rate Of Interest'])
                            * days / Decimal(basis * 100)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                if abs(expected - Decimal(row['Interest Amount'])) <= Decimal('.01'):
                    matches.append(str(basis))
            rates['/'.join(matches) or 'other'] += 1
            spans[(row['Interest Type'], row['Loan Disbursement'])].append((first, end, identifier(row)))
        overlaps = []
        for values in spans.values():
            values.sort()
            for index, left in enumerate(values):
                for right in values[index + 1:]:
                    if right[0] >= left[1]:
                        break
                    overlaps.append([left[2], right[2]])
        loan_demands = [row for row in demands if row['Loan'] == loan
                        and identifier(row) in posted['Loan Demand']]
        invalid = [identifier(row) for row in loan_demands
                   if abs(Decimal(row['Demand Amount']) - sum(Decimal(row[key] or '0')
                       for key in ('Paid Amount', 'Waived Amount', 'Outstanding Amount'))) > Decimal('.01')]
        result[loan] = {
            'posted_accruals': len(selected),
            'self_offset_accruals': sum(identifier(row) in suspect for row in selected),
            'day_count_amount_matches': dict(rates),
            'overlapping_period_pairs': overlaps,
            'posted_demands': len(loan_demands),
            'demand_subtypes': dict(Counter(row['Demand Subtype'] for row in loan_demands)),
            'demand_totals': {key: str(sum(Decimal(row[key] or '0') for row in loan_demands))
                for key in ('Demand Amount', 'Paid Amount', 'Waived Amount', 'Outstanding Amount')},
            'invalid_demand_balances': invalid,
        }
    return {'scope': 'Vouchers present in the supplied GL export; demand balances as of native export.',
            'period_convention': 'Native term periods include both dates; non-term periods exclude the start date.',
            'limitations': 'No funding-date, contract, principal-event, correction or accounting-readiness conclusion.',
            'loans': result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gl', required=True)
    parser.add_argument('--accruals', required=True)
    parser.add_argument('--demands', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = reconcile(records(args.gl), records(args.accruals), records(args.demands))
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(f"Reconciled {len(report['loans'])} loans; private report saved to {args.output}")
