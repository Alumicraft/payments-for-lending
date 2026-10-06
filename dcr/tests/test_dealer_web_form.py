"""Native Web Form boundary tests: malicious saves and private readbacks."""

import importlib
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dcr.api import dealer_web_form as form_api
from dcr.api import dealer_portal as portal


def config(**changes):
    return SimpleNamespace(name=form_api.FORM_NAME, doc_type=form_api.DOCTYPE,
                           published=1, login_required=1, anonymous=0, **changes)


class TestDealerWebForm(unittest.TestCase):
    @patch.object(form_api, "frappe")
    @patch.object(portal, "save_hbr_draft")
    @patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
    def test_native_save_returns_only_name_and_uses_scoped_draft_service(self, identity, save, frappe):
        frappe.get_doc.return_value = config()
        save.return_value = {"name": "HBR-A", "loan": {"internal": "private"}}
        result = form_api.accept(form_api.FORM_NAME, json.dumps({
            "name": "HBR-A", "doctype": form_api.DOCTYPE, "web_form_name": form_api.FORM_NAME,
            "modified": "2026-10-05T12:00:00", "factory": "FACTORY-A", "home_type": "Inventory",
        }))
        self.assertEqual(result, {"name": "HBR-A", "doctype": form_api.DOCTYPE})
        save.assert_called_once_with(payload={"factory": "FACTORY-A", "home_type": "Inventory"},
                                    name="HBR-A", expected_modified="2026-10-05T12:00:00")

    @patch.object(form_api, "frappe")
    @patch.object(portal, "save_hbr_draft")
    @patch.object(portal, "get_current_dealer_customer")
    @patch.object(portal, "_deny", side_effect=ValueError)
    def test_staff_fields_and_forged_customer_are_rejected(self, deny, identity, save, frappe):
        frappe.get_doc.return_value = config()
        for field in ("customer", "docstatus", "custom_portal_status", "in_storage", "doc_checklist", "owner"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                form_api.accept(form_api.FORM_NAME, {field: "FORGED"})
        save.assert_not_called()

    @patch.object(form_api, "frappe")
    @patch.object(portal, "save_hbr_draft")
    @patch.object(portal, "get_current_dealer_customer", side_effect=ValueError)
    def test_guest_unmapped_disabled_or_ambiguous_identity_cannot_save(self, identity, save, frappe):
        frappe.get_doc.return_value = config()
        with self.assertRaises(ValueError):
            form_api.accept(form_api.FORM_NAME, {"factory": "FACTORY-A"})
        save.assert_not_called()

    @patch.object(form_api, "frappe")
    @patch.object(portal, "_deny", side_effect=ValueError)
    def test_unpublished_or_public_configuration_and_request_keys_fail_closed(self, deny, frappe):
        for field, value in (("published", 0), ("login_required", 0), ("anonymous", 1), ("doc_type", "Customer")):
            candidate = config()
            setattr(candidate, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                form_api.require_form(candidate)
        with self.assertRaises(ValueError):
            form_api.require_form(config(), "FORGED-REQUEST-KEY")

    def test_metadata_and_select_options_follow_current_doctype(self):
        hbr = json.loads((Path(__file__).parents[1] / "dcr/doctype/home_build_request/home_build_request.json").read_text())
        byname = {field["fieldname"]: field for field in hbr["fields"]}
        byname["home_type"]["options"] += "\nFuture Type"
        fields = form_api.build_fields(SimpleNamespace(fields=[byname[name] for name in hbr["field_order"]]),
                                       [{"name": "FACTORY-A", "label": "Factory A"}])
        actual = {field["fieldname"]: field for field in fields}
        self.assertIn("Future Type", actual["home_type"]["options"])
        self.assertEqual(actual["factory"]["options"], "\nFACTORY-A")
        self.assertEqual(actual["factory"]["fieldtype"], "Select")
        self.assertEqual(actual["community_details_section"]["depends_on"], "eval:doc.property_type=='Park'")
        for forbidden in ("customer", "owner", "in_storage", "home_buyer", "escrow_company", "broker", "doc_checklist"):
            self.assertNotIn(forbidden, actual)
        self.assertEqual(set(actual) & portal.HBR_INPUT_FIELDS, portal.HBR_INPUT_FIELDS)
        self.assertNotEqual(fields[0]["fieldtype"], "Column Break")

    def test_reference_doc_excludes_staff_fields_and_child_table(self):
        result = form_api.reference_values({"name": "HBR-A", "quote_no": "QUOTE-A", "customer": "DEALER-A",
                                           "doc_checklist": [{"waived": 1}], "internal_note": "PRIVATE", "in_storage": 1})
        self.assertEqual(result["quote_no"], "QUOTE-A")
        for forbidden in ("customer", "doc_checklist", "internal_note", "in_storage", "owner"):
            self.assertNotIn(forbidden, result)

    @patch.object(form_api, "frappe")
    @patch.object(form_api, "configure_fields")
    @patch.object(portal, "_get_owned_hbr", side_effect=ValueError)
    @patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
    def test_native_data_endpoint_uses_customer_ownership_for_staff_created_records(self, identity, owned, fields, frappe):
        frappe.get_doc.return_value = config()
        frappe.get_doc.return_value.as_dict = lambda: {}
        with self.assertRaises(ValueError):
            form_api.get_form_data(form_api.DOCTYPE, "HBR-B", form_api.FORM_NAME)
        owned.assert_called_once_with("HBR-B", {"name": "DEALER-A"})

    @patch.object(form_api, "frappe")
    @patch.object(portal, "get_current_dealer_customer")
    @patch.object(portal, "_deny", side_effect=ValueError)
    def test_native_data_endpoint_cannot_be_used_to_fetch_another_doctype(self, deny, identity, frappe):
        frappe.get_doc.return_value = config()
        with self.assertRaises(ValueError):
            form_api.get_form_data("Customer", "OTHER-DEALER", form_api.FORM_NAME)

    def test_other_native_forms_keep_native_save_and_read_behavior(self):
        native = MagicMock()
        with patch.dict(sys.modules, {"frappe.website.doctype.web_form.web_form": native}):
            form_api.accept("other-form", '{"field":"value"}', "request-key")
            native.accept.assert_called_once_with("other-form", '{"field":"value"}', "request-key")
            form_api.get_form_data("Other DocType", "OTHER-1", "other-form", "request-key")
            native.get_form_data.assert_called_once_with("Other DocType", "OTHER-1", "other-form", "request-key")

    @patch.object(portal, "frappe")
    @patch.object(portal, "_serialize_hbr")
    @patch.object(portal, "_get_owned_hbr")
    @patch.object(portal, "get_current_dealer_customer")
    def test_stale_edit_and_new_review_lock_are_checked_after_reload(self, identity, owned, serialize, frappe):
        hbr = MagicMock()
        hbr.get.side_effect = lambda field: {"docstatus": 0, "custom_portal_status": "Submitted for Review",
                                           "modified": datetime(2026, 10, 5, 12)}.get(field)
        owned.return_value = hbr
        frappe.throw.side_effect = ValueError
        with self.assertRaises(ValueError):
            portal.save_hbr_draft({"quote_no": "changed"}, "HBR-A", "2026-10-05T11:00:00")
        hbr.reload.assert_called_once()
        hbr.save.assert_not_called()
        hbr.get.side_effect = lambda field: {"docstatus": 0, "custom_portal_status": "Draft",
                                           "modified": datetime(2026, 10, 5, 12)}.get(field)
        with self.assertRaises(ValueError):
            portal.save_hbr_draft({"quote_no": "changed"}, "HBR-A", "2026-10-05T11:00:00")
        hbr.save.assert_not_called()


class TestNativeRendererGuard(unittest.TestCase):
    def setUp(self):
        class BaseWebForm:
            def get_context(self, context):
                context.native_called = True
            def load_form_data(self, context, request=None):
                context.reference_doc = {"internal_note": "PRIVATE"}
            def get_web_form_request(self, key=None, **kwargs):
                return "native-request"
            def has_web_form_permission(self, doctype, name, ptype):
                return "native-permission"
        native = SimpleNamespace(WebForm=BaseWebForm)
        with patch.dict(sys.modules, {"frappe.website.doctype.web_form.web_form": native}):
            self.module = importlib.import_module("dcr.overrides.dealer_web_form")
        self.form = self.module.DealerWebForm()
        self.form.__dict__.update(vars(config()))

    @patch.object(form_api, "configure_fields")
    @patch.object(portal, "_require_editable_hbr", side_effect=ValueError)
    @patch.object(portal, "_get_owned_hbr", return_value={"name": "HBR A"})
    @patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
    @patch.object(form_api, "require_form")
    def test_locked_owned_edit_link_returns_to_read_only_portal(self, require, identity, owned, editable, fields):
        class Redirect(Exception):
            pass
        context = SimpleNamespace()
        with patch.object(self.module, "frappe") as frappe:
            frappe.ValidationError = ValueError
            frappe.Redirect = Redirect
            frappe.session.user = "dealer@example.test"
            frappe.form_dict.get.side_effect = lambda key: {"name": "HBR A", "is_edit": True}.get(key)
            frappe.form_dict.name = "HBR A"
            with self.assertRaises(Redirect):
                self.form.get_context(context)
            self.assertEqual(frappe.local.flags.redirect_location, "/portal#/request/HBR%20A")
        owned.assert_called_once_with("HBR A", {"name": "DEALER-A"})
        fields.assert_not_called()
        self.assertFalse(getattr(context, "native_called", False))

    @patch.object(portal, "_require_editable_hbr")
    @patch.object(portal, "_get_owned_hbr", side_effect=ValueError)
    @patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
    @patch.object(form_api, "require_form")
    def test_foreign_edit_link_never_reaches_locked_record_redirect(self, require, identity, owned, editable):
        with patch.object(self.module, "frappe") as frappe:
            frappe.ValidationError = ValueError
            frappe.local.flags = SimpleNamespace(redirect_location=None)
            frappe.session.user = "dealer@example.test"
            frappe.form_dict.get.side_effect = lambda key: {"name": "OTHER-HBR", "is_edit": True}.get(key)
            frappe.form_dict.name = "OTHER-HBR"
            with self.assertRaises(ValueError):
                self.form.get_context(SimpleNamespace())
            self.assertIsNone(frappe.local.flags.redirect_location)
        editable.assert_not_called()

    @patch.object(portal, "_require_editable_hbr", side_effect=ValueError)
    @patch.object(portal, "_get_owned_hbr")
    def test_owned_record_cannot_bypass_review_lock_via_native_write_permission(self, owned, editable):
        with self.assertRaises(ValueError):
            self.form.has_web_form_permission(form_api.DOCTYPE, "HBR-A", "write")
        owned.assert_called_once_with("HBR-A")

    @patch.object(portal, "_get_owned_hbr", side_effect=ValueError)
    def test_owner_or_staff_role_does_not_bypass_customer_scope(self, owned):
        with self.assertRaises(ValueError):
            self.form.has_web_form_permission(form_api.DOCTYPE, "HBR-B")

    @patch.object(portal, "_get_owned_hbr", return_value={"name": "HBR-A", "quote_no": "QUOTE-A"})
    def test_renderer_scrubs_full_native_reference_doc(self, owned):
        context = SimpleNamespace()
        with patch.object(self.module, "frappe") as frappe:
            frappe.form_dict.get.return_value = "HBR-A"
            frappe.form_dict.name = "HBR-A"
            self.form.load_form_data(context)
        self.assertNotIn("internal_note", context.reference_doc)
        self.assertEqual(context.reference_doc["name"], "HBR-A")

    def test_other_web_forms_keep_native_renderer_permissions(self):
        self.form.name = "other-form"
        context = SimpleNamespace()
        self.form.get_context(context)
        self.assertTrue(context.native_called)
        self.assertEqual(self.form.has_web_form_permission("Other", "OTHER-1"), "native-permission")
