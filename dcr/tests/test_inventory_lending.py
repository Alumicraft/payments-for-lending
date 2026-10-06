"""Inventory must survive native application validation and shared prints."""

import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import Environment


@pytest.mark.parametrize("override", [False, True])
def test_inventory_metadata_repair_preserves_choices_and_is_idempotent(override):
    from dcr.setup import ensure_inventory_loan_application_fields

    values = {
        ("Custom Field", "home-type", "options"): "\nSpec\nCustomer Sold\nLegacy",
        ("Custom Field", "projection", "depends_on"): "eval:doc.home_type=='Spec'",
    }
    if override:
        values[("Property Setter", "override", "value")] = "Spec\nCustomer Sold"
    fake = MagicMock()

    def exists(doctype, filters):
        if doctype == "Property Setter":
            return "override" if override else None
        return {"home_type": "home-type", "advance_preapproval_section": "projection"}.get(filters["fieldname"])

    fake.db.exists.side_effect = exists
    fake.db.get_value.side_effect = lambda dt, name, field: values[(dt, name, field)]
    fake.db.set_value.side_effect = lambda dt, name, field, value: values.__setitem__((dt, name, field), value)
    with patch("dcr.setup.frappe", fake):
        ensure_inventory_loan_application_fields()
        first_writes = fake.db.set_value.call_count
        ensure_inventory_loan_application_fields()
    assert values[("Custom Field", "home-type", "options")] == "\nSpec\nCustomer Sold\nLegacy\nInventory"
    if override:
        assert values[("Property Setter", "override", "value")] == "Spec\nCustomer Sold\nInventory"
    assert "Inventory" in values[("Custom Field", "projection", "depends_on")]
    assert fake.db.set_value.call_count == first_writes
    fake.clear_cache.assert_called_once_with(doctype="Loan Application")


def test_inventory_application_defaults_keep_the_hbr_type():
    from dcr.api.lending import _get_loan_application_hbr_defaults

    result = _get_loan_application_hbr_defaults({
        "name": "HBR-INVENTORY", "customer": "DEMO DEALER",
        "home_type": "Inventory", "home_invoice_plus_freight": 200000,
    })
    assert result["home_type"] == "Inventory"
    assert result["home_build_request"] == "HBR-INVENTORY"
    assert result["loan_amount"] == 200000


def render_print(format_name, home_type):
    root = Path(__file__).resolve().parents[1] / "dcr" / "print_format"
    data = json.loads((root / format_name / f"{format_name}.json").read_text())
    doc = defaultdict(lambda: None, {
        "name": "DEMO-INVENTORY", "home_type": home_type,
        "home_build_request": "HBR-INVENTORY", "customer": "DEMO DEALER",
        "applicant": "DEMO DEALER", "loan_amount": 200000,
        "home_invoice_plus_freight": 200000, "floor_plan": "DEMO MODEL",
        "property_type": "Private Property", "financing_type": "Floored",
        "custom_projected_sales_price": 250000, "custom_projected_equity": 50000,
        "custom_projected_ltv": 80, "home_serial_no": "DEMO SERIAL",
    })
    def lookup(doctype, name, field, **kwargs):
        if isinstance(field, list):
            return defaultdict(lambda: None)
        return "Demo Dealer" if doctype == "Customer" else "Demo Factory"
    fake = SimpleNamespace(
        db=SimpleNamespace(get_value=lookup),
        get_doc=lambda *args: defaultdict(lambda: None),
        utils=SimpleNamespace(fmt_money=lambda amount, **kwargs: f"${float(amount or 0):,.2f}", formatdate=lambda date, *args: str(date)),
    )
    return Environment().from_string(data["html"]).render(doc=doc, frappe=fake)


@pytest.mark.parametrize("home_type", ["Spec", "Inventory", "Customer Sold"])
def test_shared_preapproval_renders_the_correct_type_and_sections(home_type):
    html = render_print("advance_pre_approval", home_type)
    title = f"{home_type} Home Flooring Request" if home_type != "Customer Sold" else "Customer Sold Flooring Request"
    assert title in html
    assert ("Projected investment" in html) == (home_type in ("Spec", "Inventory"))
    assert ("Customer deposit" in html) == (home_type == "Customer Sold")
    assert "$200,000.00" in html


def test_inventory_hbr_print_excludes_retail_buyer_and_escrow_sections():
    html = render_print("new_home_info_sheet", "Inventory")
    assert "Inventory New Home Info Sheet" in html
    assert '<th colspan="2">Customer Information</th>' not in html
    assert '<th colspan="2">Escrow Information</th>' not in html
    assert "DEMO MODEL" in html
    assert "$200,000.00" in html
