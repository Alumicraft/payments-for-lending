"""Staff pilot fields and deliberate factory sending."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import Environment, ChainableUndefined
from dcr.api import factory_packets, pilot_fields
from dcr.dcr.doctype.factory_assignment.factory_assignment import FactoryAssignment

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("status", ["Not Submitted", "Approved"])
def test_submitting_factory_assignment_never_sends_email(status):
    assignment = FactoryAssignment()
    assignment.retailer_application_status = status
    assignment.send_retailer_application = MagicMock()
    assignment.db_set = MagicMock()
    assignment.on_submit()
    assignment.send_retailer_application.assert_not_called()
    assignment.db_set.assert_not_called()


@patch.object(factory_packets, "require_staff")
@patch.object(factory_packets, "frappe")
@pytest.mark.parametrize("docstatus,status", [(0, "Not Submitted"), (2, "Not Submitted"), (1, "Approved"), (1, "Submitted"), (1, "Rejected")])
def test_factory_send_rejects_drafts_cancelled_and_already_sent(frappe, staff, docstatus, status):
    assignment = frappe.get_doc.return_value
    assignment.docstatus = docstatus
    assignment.retailer_application_status = status
    frappe.throw.side_effect = ValueError
    with pytest.raises(ValueError):
        factory_packets.send_packet("FA-A")
    assignment.send_retailer_application.assert_not_called()
    assignment.db_set.assert_not_called()


@patch.object(factory_packets, "require_staff")
@patch.object(factory_packets, "frappe")
def test_factory_send_reads_locked_server_document_and_marks_only_success(frappe, staff):
    assignment = frappe.get_doc.return_value
    assignment.docstatus = 1
    assignment.retailer_application_status = "Not Submitted"
    factory_packets.send_packet("FA-A")
    staff.assert_any_call("Factory Assignment", "FA-A", "write")
    staff.assert_any_call("Factory Assignment", "FA-A", "email")
    assert "FOR UPDATE" in frappe.db.sql.call_args.args[0]
    assert frappe.db.sql.call_args.args[1] == ("FA-A",)
    frappe.get_doc.assert_called_once_with("Factory Assignment", "FA-A")
    assignment.send_retailer_application.assert_called_once()
    assignment.db_set.assert_called_once_with("retailer_application_status", "Submitted")
    assignment.reset_mock()
    assignment.send_retailer_application.side_effect = ValueError("missing dealer documents")
    with pytest.raises(ValueError):
        factory_packets.send_packet("FA-A")
    assignment.db_set.assert_not_called()


@patch.object(factory_packets, "require_staff", side_effect=PermissionError)
@patch.object(factory_packets, "frappe")
def test_factory_send_checks_staff_access_before_reading_or_sending(frappe, staff):
    with pytest.raises(PermissionError):
        factory_packets.send_packet("FA-A")
    frappe.get_doc.assert_not_called()
    frappe.db.sql.assert_not_called()


@patch.object(pilot_fields, "frappe")
def test_setup_adds_missing_fields_once_and_preserves_existing_site_fields(frappe):
    installed = set()
    frappe.db.exists.return_value = True
    frappe.get_meta.side_effect = lambda dt: SimpleNamespace(has_field=lambda field: (dt, field) in installed)
    frappe.get_doc.side_effect = lambda field: SimpleNamespace(insert=lambda **kw: installed.add((field["dt"], field["fieldname"])))
    pilot_fields.ensure_pilot_fields()
    pilot_fields.ensure_pilot_fields()
    assert installed == {("Loan Application", "monthly_insurance_amount"), ("Purchase Order", "custom_dcr_dealer")}
    assert frappe.get_doc.call_count == 2
    frappe.db.set_value.assert_not_called()


@patch.object(pilot_fields, "frappe")
def test_purchase_order_dealer_tracks_changed_or_removed_home_reference(frappe):
    frappe.get_meta.return_value.has_field.return_value = True
    frappe.db.get_value.return_value = "DEALER-B"
    doc = SimpleNamespace(custom_dcr_dealer="DEALER-A", get=lambda field: "HBR-B")
    pilot_fields.populate_purchase_order_dealer(doc)
    assert doc.custom_dcr_dealer == "DEALER-B"
    doc.get = lambda field: None
    pilot_fields.populate_purchase_order_dealer(doc)
    assert doc.custom_dcr_dealer is None


@patch.object(pilot_fields, "frappe")
def test_po_layout_moves_only_dcr_context_and_is_repeatable(frappe):
    fields = {}
    for name in ("custom_home_build_request", "custom_dcr_dealer", "custom_payment_type"):
        field = MagicMock()
        values = {"insert_after": "connections_tab", "reqd": 1, "description": "Site instruction"}
        field.get.side_effect = values.get
        field.set.side_effect = values.__setitem__
        fields[name] = field
    frappe.db.exists.side_effect = lambda dt, filters: filters["fieldname"]
    frappe.get_doc.side_effect = lambda dt, name: fields[name]
    pilot_fields.ensure_purchase_order_form_layout()
    pilot_fields.ensure_purchase_order_form_layout()
    for field in fields.values():
        field.save.assert_called_once_with(ignore_permissions=True)
        assert field.get("reqd") == 1
        assert field.get("description") == "Site instruction"
    assert fields["custom_home_build_request"].get("insert_after") == "supplier_section"
    assert fields["custom_dcr_dealer"].get("fetch_from") == "custom_home_build_request.customer"
    assert fields["custom_payment_type"].get("insert_after") == "custom_dcr_dealer"
    frappe.clear_cache.assert_called_once_with(doctype="Purchase Order")


@patch.object(pilot_fields, "frappe")
def test_po_layout_skips_missing_custom_fields(frappe):
    frappe.db.exists.return_value = None
    pilot_fields.ensure_purchase_order_form_layout()
    frappe.get_doc.assert_not_called()
    frappe.clear_cache.assert_not_called()


@patch.object(pilot_fields, "frappe")
def test_po_layout_updates_saved_field_order_without_reordering_site_fields(frappe):
    context = ("custom_home_build_request", "custom_dcr_dealer", "custom_payment_type")
    fields = {}
    for name in context:
        values = {"insert_after": "connections_tab"}
        field = MagicMock()
        field.get.side_effect = values.get
        field.set.side_effect = values.__setitem__
        fields[name] = field
    original = ["supplier_section", "naming_series", "supplier", "site_reference",
                "items_section", "items", "connections_tab", "custom_home_build_request"]
    setter = MagicMock()
    setter.value = json.dumps(original)
    frappe.db.exists.side_effect = lambda dt, filters: filters["fieldname"]
    frappe.get_all.return_value = [SimpleNamespace(name="Purchase Order-main-field_order")]
    frappe.get_doc.side_effect = lambda dt, name: setter if dt == "Property Setter" else fields[name]

    pilot_fields.ensure_purchase_order_form_layout()
    pilot_fields.ensure_purchase_order_form_layout()

    revised = json.loads(setter.value)
    assert revised[:4] == ["supplier_section", *context]
    assert [name for name in revised if name not in context] == [name for name in original if name not in context]
    setter.save.assert_called_once_with(ignore_permissions=True)


@patch.object(pilot_fields, "frappe")
def test_insurance_moves_out_of_projections_without_changing_rules_or_site_order(frappe):
    values = {"insert_after": "custom_projected_ltv", "reqd": 1,
              "read_only": 0, "allow_on_submit": 0, "description": "Staff instruction"}
    field = MagicMock()
    field.get.side_effect = values.get
    field.set.side_effect = values.__setitem__
    original = ["projections", "custom_projected_ltv", "monthly_insurance_amount",
                "site_note", "loan_calculations", "repayment_amount", "total_payable_amount", "connections"]
    setter = MagicMock(value=json.dumps(original))
    frappe.db.exists.return_value = "Loan Application-monthly_insurance_amount"
    frappe.get_meta.return_value.has_field.return_value = True
    frappe.get_all.return_value = [SimpleNamespace(name="Loan Application-main-field_order")]
    frappe.get_doc.side_effect = lambda dt, name: field if dt == "Custom Field" else setter

    pilot_fields.ensure_loan_application_insurance_layout()
    pilot_fields.ensure_loan_application_insurance_layout()

    assert values == {"insert_after": "repayment_amount", "reqd": 1,
                      "read_only": 0, "allow_on_submit": 0, "description": "Staff instruction"}
    revised = json.loads(setter.value)
    assert revised[revised.index("repayment_amount") + 1] == "monthly_insurance_amount"
    assert [value for value in revised if value != "monthly_insurance_amount"] == [
        value for value in original if value != "monthly_insurance_amount"]
    field.save.assert_called_once_with(ignore_permissions=True)
    setter.save.assert_called_once_with(ignore_permissions=True)
    frappe.clear_cache.assert_called_once_with(doctype="Loan Application")
    frappe.db.set_value.assert_not_called()


@patch.object(pilot_fields, "frappe")
def test_insurance_layout_waits_for_field_and_payment_anchor(frappe):
    frappe.db.exists.return_value = None
    pilot_fields.ensure_loan_application_insurance_layout()
    frappe.db.exists.return_value = "Loan Application-monthly_insurance_amount"
    frappe.get_meta.return_value.has_field.return_value = False
    pilot_fields.ensure_loan_application_insurance_layout()
    frappe.get_doc.assert_not_called()
    frappe.clear_cache.assert_not_called()


def test_offline_date_is_audited_editable_after_submission_and_staff_owned():
    from dcr.api.dealer_portal import HBR_INPUT_FIELDS
    data = json.loads((ROOT / "dcr/doctype/home_build_request/home_build_request.json").read_text())
    field = next(row for row in data["fields"] if row["fieldname"] == "offline_date")
    assert data["track_changes"] == 1
    assert field["allow_on_submit"] == 1
    assert "offline_date" not in HBR_INPUT_FIELDS


def test_staff_insurance_amount_reaches_ach_packet_print():
    source = json.loads((ROOT / "dcr/print_format/ach_recurring_payment_authorization/ach_recurring_payment_authorization.json").read_text())
    environment = Environment(undefined=ChainableUndefined)
    frappe = SimpleNamespace(db=SimpleNamespace(get_value=lambda *args, **kw: {}), utils=SimpleNamespace(
        fmt_money=lambda amount, **kw: f"${float(amount):,.2f}", formatdate=lambda *args: ""))
    html = environment.from_string(source["html"]).render(doc={"monthly_insurance_amount": 175.25}, frappe=frappe)
    assert "Approximate monthly insurance" in html
    assert "$175.25" in html


@patch("dcr.setup.ensure_order_hbr_fields")
@patch("dcr.patches.backfill_purchase_order_dealer.ensure_pilot_fields")
@patch("dcr.patches.backfill_purchase_order_dealer.frappe")
def test_dealer_backfill_skips_missing_columns_and_only_fills_missing_context(frappe, fields, links):
    from dcr.patches.backfill_purchase_order_dealer import execute
    frappe.db.has_column.return_value = False
    execute()
    frappe.db.sql.assert_not_called()
    frappe.db.has_column.return_value = True
    execute()
    query = frappe.db.sql.call_args.args[0]
    assert "hbr.name = po.custom_home_build_request" in query
    assert "COALESCE(po.custom_dcr_dealer, '') = ''" in query
    assert "COALESCE(hbr.customer, '') != ''" in query
    frappe.db.commit.assert_called_once()
