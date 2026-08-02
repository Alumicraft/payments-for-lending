"""Security and workflow tests for the dealer portal service layer."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestDealerPortalPage(unittest.TestCase):

    @patch("dcr.www.dealer_portal.frappe")
    def test_guest_goes_directly_to_frappe_login(self, mock_frappe):
        from dcr.www.dealer_portal import get_context

        class Redirect(Exception):
            pass

        mock_frappe.Redirect = Redirect
        mock_frappe.session.user = "Guest"

        with self.assertRaises(Redirect):
            get_context(MagicMock())

        self.assertEqual(
            mock_frappe.local.flags.redirect_location,
            "/login?redirect-to=/portal",
        )

    @patch("dcr.www.dealer_portal.frappe")
    def test_signed_in_user_renders_portal(self, mock_frappe):
        from dcr.www.dealer_portal import get_context

        mock_frappe.session.user = "dealer@example.test"
        mock_frappe.session.csrf_token = "csrf-test"
        context = MagicMock()

        get_context(context)

        self.assertEqual(context.title, "Dealer Portal")
        self.assertEqual(context.portal_user, "dealer@example.test")
        self.assertEqual(context.csrf_token, "csrf-test")


class TestDealerPortalIdentity(unittest.TestCase):

    @patch("dcr.api.dealer_portal.frappe")
    def test_resolves_one_active_dealer_from_standard_portal_user_rows(self, mock_frappe):
        from dcr.api.dealer_portal import get_current_dealer_customer

        mock_frappe.session.user = "dealer@example.com"
        mock_frappe.get_all.return_value = [{"parent": "DEALER-001"}]
        mock_frappe.db.get_value.return_value = {
            "name": "DEALER-001",
            "customer_name": "Demo Dealer",
            "customer_group": "Dealer",
            "disabled": 0,
            "email_id": "dealer@example.com",
        }

        result = get_current_dealer_customer()

        self.assertEqual(result["name"], "DEALER-001")
        mock_frappe.get_all.assert_called_once_with(
            "Portal User",
            filters={"parenttype": "Customer", "user": "dealer@example.com"},
            fields=["parent"],
            ignore_permissions=True,
            limit_page_length=0,
        )

    @patch("dcr.api.dealer_portal.frappe")
    def test_guest_cannot_resolve_dealer_context(self, mock_frappe):
        from dcr.api.dealer_portal import get_current_dealer_customer

        mock_frappe.session.user = "Guest"
        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            get_current_dealer_customer()

        mock_frappe.get_all.assert_not_called()

    @patch("dcr.api.dealer_portal.frappe")
    def test_multiple_customer_memberships_fail_closed(self, mock_frappe):
        from dcr.api.dealer_portal import get_current_dealer_customer

        mock_frappe.session.user = "dealer@example.com"
        mock_frappe.get_all.return_value = [
            {"parent": "DEALER-001"},
            {"parent": "DEALER-002"},
        ]
        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            get_current_dealer_customer()

        mock_frappe.db.get_value.assert_not_called()


class TestDealerPortalHBRWorkflow(unittest.TestCase):

    def _customer(self):
        return {
            "name": "DEALER-001",
            "customer_name": "Demo Dealer",
            "customer_group": "Dealer",
            "disabled": 0,
            "email_id": "dealer@example.com",
        }

    @patch("dcr.api.dealer_portal._serialize_hbr", return_value={"name": "HBR-001"})
    @patch("dcr.api.dealer_portal._has_field", return_value=True)
    @patch("dcr.api.dealer_portal._require_active_factory")
    @patch("dcr.api.dealer_portal.get_current_dealer_customer")
    @patch("dcr.api.dealer_portal.frappe")
    def test_new_draft_sets_customer_server_side(
        self,
        mock_frappe,
        mock_customer,
        mock_factory,
        mock_has_field,
        mock_serialize,
    ):
        from dcr.api.dealer_portal import save_hbr_draft

        mock_customer.return_value = self._customer()
        hbr = MagicMock()
        hbr.name = "HBR-001"
        mock_frappe.new_doc.return_value = hbr

        result = save_hbr_draft(
            payload='{"home_type":"Spec","financing_type":"Cash","property_type":"Park","factory":"FACTORY-001"}'
        )

        self.assertEqual(result, {"name": "HBR-001"})
        self.assertEqual(hbr.customer, "DEALER-001")
        hbr.set.assert_any_call("home_type", "Spec")
        hbr.set.assert_any_call("factory", "FACTORY-001")
        hbr.insert.assert_called_once_with(ignore_permissions=True)
        mock_factory.assert_called_once_with("DEALER-001", "FACTORY-001")

    @patch("dcr.api.dealer_portal._serialize_hbr", return_value={"name": "HBR-001"})
    @patch("dcr.api.dealer_portal._require_active_factory")
    @patch("dcr.api.dealer_portal.get_current_dealer_customer")
    @patch("dcr.api.dealer_portal._get_owned_hbr")
    def test_existing_draft_cannot_clear_assigned_factory(
        self,
        mock_owned_hbr,
        mock_customer,
        mock_factory,
        mock_serialize,
    ):
        from dcr.api.dealer_portal import save_hbr_draft

        mock_customer.return_value = self._customer()
        mock_owned_hbr.return_value = SimpleNamespace(
            docstatus=0,
            custom_portal_status="Draft",
            factory="FACTORY-001",
            name="HBR-001",
        )
        mock_factory.side_effect = ValueError

        with self.assertRaises(ValueError):
            save_hbr_draft(payload='{"factory":""}', name="HBR-001")

        mock_factory.assert_called_once_with("DEALER-001", "")

    @patch("dcr.api.dealer_portal.frappe")
    def test_arbitrary_customer_field_is_rejected(self, mock_frappe):
        from dcr.api.dealer_portal import _parse_payload

        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            _parse_payload({"customer": "SOMEONE-ELSE"})

    @patch("dcr.api.dealer_portal.frappe")
    def test_owned_hbr_check_rejects_other_dealer(self, mock_frappe):
        from dcr.api.dealer_portal import _get_owned_hbr

        mock_frappe.db.exists.return_value = None
        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            _get_owned_hbr("HBR-001", {"name": "DEALER-001"})

        mock_frappe.db.exists.assert_called_once_with(
            "Home Build Request",
            {"name": "HBR-001", "customer": "DEALER-001"},
        )
        mock_frappe.get_doc.assert_not_called()

    @patch("dcr.api.dealer_portal._serialize_hbr", return_value={"name": "HBR-001", "portal_status": "Submitted for Review"})
    @patch("dcr.api.dealer_portal._has_field", return_value=True)
    @patch("dcr.api.dealer_portal.get_current_dealer_customer")
    @patch("dcr.api.dealer_portal._get_owned_hbr")
    @patch("dcr.api.dealer_portal.frappe")
    def test_submit_for_review_does_not_submit_or_lock_hbr(
        self,
        mock_frappe,
        mock_owned_hbr,
        mock_customer,
        mock_has_field,
        mock_serialize,
    ):
        from dcr.api.dealer_portal import submit_hbr_for_review

        mock_customer.return_value = self._customer()
        hbr = SimpleNamespace(
            docstatus=0,
            custom_portal_status="Draft",
            name="HBR-001",
            reload=lambda: None,
        )
        mock_owned_hbr.return_value = hbr
        mock_frappe.session.user = "dealer@example.com"
        mock_frappe.utils.now_datetime.return_value = "2026-08-01 12:00:00"

        result = submit_hbr_for_review("HBR-001")

        self.assertEqual(result["portal_status"], "Submitted for Review")
        mock_frappe.db.set_value.assert_called_once()
        updates = mock_frappe.db.set_value.call_args.args[2]
        self.assertEqual(updates["custom_portal_status"], "Submitted for Review")
        self.assertNotIn("submit", dir(hbr))

    @patch("dcr.api.dealer_portal._has_field", return_value=False)
    @patch("dcr.api.dealer_portal.get_current_dealer_customer")
    @patch("dcr.api.dealer_portal._get_owned_hbr")
    @patch("dcr.api.dealer_portal.frappe")
    def test_submit_for_review_fails_closed_before_native_status_fallback(
        self,
        mock_frappe,
        mock_owned_hbr,
        mock_customer,
        mock_has_field,
    ):
        from dcr.api.dealer_portal import submit_hbr_for_review

        mock_customer.return_value = self._customer()
        mock_owned_hbr.return_value = SimpleNamespace(
            docstatus=0,
            custom_portal_status="Draft",
            name="HBR-001",
        )
        mock_frappe.throw.side_effect = ValueError

        with self.assertRaises(ValueError):
            submit_hbr_for_review("HBR-001")

        mock_frappe.db.set_value.assert_not_called()

    @patch("dcr.api.dealer_portal.frappe")
    def test_upload_validation_rejects_executable_extension(self, mock_frappe):
        from dcr.api.dealer_portal import _validate_upload

        mock_frappe.throw.side_effect = ValueError
        upload = SimpleNamespace(filename="malware.exe", mimetype="application/octet-stream", read=lambda: b"x")

        with self.assertRaises(ValueError):
            _validate_upload(upload)


if __name__ == "__main__":
    unittest.main()
