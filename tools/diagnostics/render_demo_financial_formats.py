"""Render synthetic local HTML for PDF/layout checks; never calls Frappe."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from jinja2 import ChainableUndefined, Environment


def render(destination):
    root = Path(__file__).resolve().parents[2]
    destination.mkdir(parents=True, exist_ok=True)
    def lookup(doctype, *args, **kwargs):
        return {
            'Customer': dict(customer_name='Portal Test'),
            'Company': dict(email='accounting@dealercapital.net', phone_no='8004541116'),
            'Supplier': 'Champion Home Builders',
            'Home Build Request': dict(factory='Champion Home Builders'),
        }.get(doctype, {})
    frappe = SimpleNamespace(db=SimpleNamespace(get_value=lookup),
        utils=SimpleNamespace(fmt_money=lambda x, **kw: f'${float(x):,.2f}',
                              formatdate=lambda x, *args: str(x)))
    doc = dict(name='ACC-LOAP-DEMO', company='Dealer Capital Resources', applicant='DEMO DEALER',
               loan_amount=280000, financed_invoice='DEMO INVOICE', financed_invoice_date='2026-10-11',
               home_build_request='DEMO HOME')
    quote = dict(available=True, date='2028-01-15', principal=220500, interest=1029,
                 penalty=0, charges=0, total=221529)
    env = Environment(undefined=ChainableUndefined)
    env.globals['flooring_payoff_quote'] = lambda *args: quote
    for name in ('exhibit_a_receipt', 'dealer_flooring_loan_payoff'):
        if name == 'dealer_flooring_loan_payoff':
            doc = dict(doc, name='ACC-LOAN-DEMO', loan_amount=220500, original_financed_principal=225000)
        source = json.loads((root / 'dcr/dcr/print_format' / name / (name+'.json')).read_text())
        html = env.from_string(source['html']).render(doc=doc, frappe=frappe)
        (destination / (name+'.html')).write_text('<!doctype html><meta charset="utf-8">'+html)


if __name__ == '__main__':
    render(Path(sys.argv[1]))
