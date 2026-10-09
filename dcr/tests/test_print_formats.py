"""Regression tests for DCR print-format source files."""

import json
from pathlib import Path


PRINT_FORMATS = Path(__file__).resolve().parents[1] / "dcr" / "print_format"


def render_financial_format(name, doc):
    from jinja2 import Environment, ChainableUndefined
    from types import SimpleNamespace
    source = json.loads((PRINT_FORMATS / name / (name + '.json')).read_text())
    frappe = SimpleNamespace(db=SimpleNamespace(get_value=lambda *args, **kwargs: {}),
        utils=SimpleNamespace(fmt_money=lambda amount, **kw: f'${float(amount):,.2f}',
                              formatdate=lambda value, *args: str(value)))
    return Environment(undefined=ChainableUndefined).from_string(source['html']).render(doc=doc,frappe=frappe)


def test_final_receipt_uses_invoice_date_and_all_in_principal():
    html = render_financial_format('exhibit_a_receipt',dict(loan_amount=225000,financed_invoice='PI',
        financed_invoice_date='2026-01-01',advance_date_requested='2026-01-20'))
    assert '2026-01-01' in html
    assert '2026-01-20' not in html
    assert '$225,000.00' in html
    assert 'plus additional financed DCR fees' in html
    assert 'actual advance shall be factory invoice' not in html


def test_ach_uses_signed_first_payment_date_instead_of_thirty_day_assumption():
    html = render_financial_format('ach_recurring_payment_authorization',dict(
        first_payment_date='2026-02-01',repayment_amount=900,monthly_insurance_amount=50))
    assert '2026-02-01' in html
    assert '$900.00' in html
    assert 'Amounts may vary each billing period' in html
    assert '30 days after the earlier' not in html


def test_undated_quote_does_not_print_an_invented_payment_date():
    html = render_financial_format('ach_recurring_payment_authorization',{})
    assert 'To be confirmed in the final invoice packet' in html


def test_ach_legal_text_is_constrained_to_the_printable_page():
    source = (
        PRINT_FORMATS
        / "ach_recurring_payment_authorization"
        / "ach_recurring_payment_authorization.json"
    )
    print_format = json.loads(source.read_text())

    assert '<div class="legal-text">' in print_format["html"]
    assert ".inv .legal-text" in print_format["css"]
    assert "width: 92% !important" in print_format["css"]
    assert "white-space: normal !important" in print_format["css"]
    assert "overflow-wrap: break-word !important" in print_format["css"]
