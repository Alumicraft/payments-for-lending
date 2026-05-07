"""Tests for setup helpers that provision DCR custom fields."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


class TestSetupCustomFields(unittest.TestCase):

    @patch("dcr.setup.frappe")
    def test_ensure_bank_account_ach_fields_creates_required_fields(self, mock_frappe):
        from dcr.setup import ensure_bank_account_ach_fields

        field_doc = MagicMock()
        mock_frappe.db.exists.return_value = False
        mock_frappe.get_doc.return_value = field_doc

        ensure_bank_account_ach_fields()

        payloads = [call.args[0] for call in mock_frappe.get_doc.call_args_list]
        fieldnames = {payload["fieldname"] for payload in payloads}

        self.assertEqual({payload["dt"] for payload in payloads}, {"Bank Account"})
        self.assertTrue({
            "custom_ach_status",
            "custom_achq_token",
            "custom_token_source",
            "custom_account_last_four",
            "custom_routing_last_4",
            "custom_verification_status",
            "custom_consent_captured",
            "custom_authorization_ip",
            "custom_authorization_date",
            "custom_sec_code",
            "custom_revocation_date",
            "custom_revocation_reason",
            "custom_legacy_ach_auth",
        }.issubset(fieldnames))

        by_fieldname = {payload["fieldname"]: payload for payload in payloads}
        self.assertEqual(by_fieldname["custom_ach_status"]["options"], "\nActive\nPaused\nRevoked\nFailed")
        self.assertEqual(by_fieldname["custom_sec_code"]["default"], "CCD")
        self.assertEqual(by_fieldname["custom_token_source"]["options"], "\nManual\nPlaid")
        self.assertEqual(field_doc.insert.call_count, len(payloads))
        mock_frappe.clear_cache.assert_called_once_with(doctype="Bank Account")

    @patch("dcr.setup.frappe")
    def test_ensure_purchase_order_hbr_field_creates_missing_field(self, mock_frappe):
        from dcr.setup import ensure_purchase_order_hbr_field

        field_doc = MagicMock()
        mock_frappe.db.exists.return_value = False
        mock_frappe.get_doc.return_value = field_doc

        ensure_purchase_order_hbr_field()

        payload = mock_frappe.get_doc.call_args.args[0]
        self.assertEqual(payload["doctype"], "Custom Field")
        self.assertEqual(payload["dt"], "Purchase Order")
        self.assertEqual(payload["fieldname"], "custom_home_build_request")
        self.assertEqual(payload["options"], "Home Build Request")
        field_doc.insert.assert_called_once_with(ignore_permissions=True)
        mock_frappe.clear_cache.assert_called_once_with(doctype="Purchase Order")

    @patch("dcr.setup.frappe")
    def test_ensure_order_hbr_fields_creates_only_missing_fields(self, mock_frappe):
        from dcr.setup import ensure_order_hbr_fields

        field_doc = MagicMock()

        def exists(doctype, filters):
            return filters["dt"] == "Purchase Receipt"

        mock_frappe.db.exists.side_effect = exists
        mock_frappe.get_doc.return_value = field_doc

        ensure_order_hbr_fields()

        payloads = [call.args[0] for call in mock_frappe.get_doc.call_args_list]
        created_by_dt = {payload["dt"]: payload for payload in payloads}

        self.assertEqual(set(created_by_dt), {"Purchase Order", "Purchase Invoice", "Payment Entry"})
        self.assertEqual(created_by_dt["Purchase Order"]["fieldname"], "custom_home_build_request")
        self.assertEqual(created_by_dt["Purchase Invoice"]["fieldname"], "home_build_request")
        self.assertEqual(created_by_dt["Payment Entry"]["fieldname"], "custom_home_build_request")
        self.assertEqual(created_by_dt["Payment Entry"]["read_only"], 0)
        self.assertEqual(created_by_dt["Payment Entry"]["no_copy"], 0)
        self.assertNotIn("Purchase Receipt", created_by_dt)
        self.assertEqual(field_doc.insert.call_count, 3)
        mock_frappe.db.set_value.assert_any_call("Custom Field", True, "read_only", 0)
        mock_frappe.db.set_value.assert_any_call("Custom Field", True, "no_copy", 0)
        mock_frappe.clear_cache.assert_any_call(doctype="Purchase Order")
        mock_frappe.clear_cache.assert_any_call(doctype="Purchase Invoice")
        mock_frappe.clear_cache.assert_any_call(doctype="Purchase Receipt")
        mock_frappe.clear_cache.assert_any_call(doctype="Payment Entry")

    def test_hbr_orders_connections_are_ordered_po_pi_pr_pe(self):
        import json

        doctype = json.loads(
            (ROOT / "dcr/dcr/doctype/home_build_request/home_build_request.json").read_text()
        )
        orders = [
            link["link_doctype"]
            for link in doctype["links"]
            if link.get("group") == "Orders"
        ]

        self.assertEqual(
            orders,
            ["Purchase Order", "Purchase Invoice", "Purchase Receipt", "Payment Entry"],
        )


class TestAchBankAccountMigration(unittest.TestCase):

    @patch("dcr.patches.migrate_ach_to_bank_account.ensure_bank_account_ach_fields")
    @patch("dcr.patches.migrate_ach_to_bank_account.frappe")
    def test_migration_provisions_bank_account_fields_before_copying_data(
        self, mock_frappe, mock_ensure_fields
    ):
        from dcr.patches.migrate_ach_to_bank_account import execute

        mock_frappe.db.exists.return_value = True
        mock_frappe.db.sql.return_value = []

        execute()

        mock_ensure_fields.assert_called_once_with()


class TestMapBlockContent(unittest.TestCase):

    def test_production_map_block_contains_preview_features(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()

        self.assertIn("dcr-legend", setup_code)
        self.assertIn("dcr-search", setup_code)
        self.assertIn("/assets/dcr/css/map.css", setup_code)
        self.assertIn("SatelliteControl", setup_code)
        self.assertIn("renderStackedHtml", setup_code)
        self.assertIn("buildLegend(map, geojson)", setup_code)
        self.assertIn("keepSearchEventLocal", setup_code)
        self.assertIn("anchor: 'bottom'", setup_code)
        self.assertNotIn("anchor: 'auto'", setup_code)
        self.assertNotIn("window._dcrShowTrailForHome", setup_code)

    def test_map_css_is_shipped_as_asset(self):
        css = (ROOT / "dcr/public/css/map.css").read_text()

        self.assertIn(".dcr-legend", css)
        self.assertIn(".dcr-search", css)
        self.assertIn(".dcr-popup", css)
        self.assertIn(".dcr-legend__check.is-checked::after", css)
        self.assertIn(".dcr-legend--dark .dcr-legend__check.is-checked::after", css)

    def test_workspace_css_forces_full_bleed_when_full_width_is_off(self):
        css = (ROOT / "dcr/public/css/workspace_fullwidth.css").read_text()

        self.assertIn("body:has(.workspace-body)", css)
        self.assertIn("body.dcr-workspace-fullbleed", css)
        self.assertIn("body[data-route^=\"Workspaces/\"] .container.page-body", css)
        self.assertIn("body.dcr-workspace-fullbleed .page-body", css)
        self.assertIn("body:has(.workspace-body) .container.page-body", css)
        self.assertIn("--dcr-workspace-content-padding: clamp(16px, 1.5vw, 24px)", css)
        self.assertIn("padding-left: var(--dcr-workspace-content-padding, 20px) !important", css)
        self.assertIn("padding-right: var(--dcr-workspace-content-padding, 20px) !important", css)
        self.assertIn('body[data-route="Workspaces/Map"] .container.page-body', css)
        self.assertIn("box-sizing: border-box !important", css)
        self.assertNotIn("margin-left: 0 !important", css)
        self.assertNotIn("margin-right: 0 !important", css)
        self.assertIn('body[data-route="Workspaces/Map"] .widget.custom-block-widget-box', css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"] .workspace-body", css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"] .codex-editor", css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"] .ce-block,", css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"] .ce-block__content", css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"] .widget,", css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"] .number-card", css)


class TestPackagingConfig(unittest.TestCase):

    def test_pyproject_packages_desk_assets_for_frappe_cloud(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        setup_py = (ROOT / "setup.py").read_text()
        manifest = (ROOT / "MANIFEST.in").read_text()
        hooks = (ROOT / "dcr/hooks.py").read_text()

        self.assertIn('build-backend = "setuptools.build_meta"', pyproject)
        self.assertIn('[tool.setuptools.package-data]', pyproject)
        self.assertIn('"public/js/*.js"', pyproject)
        self.assertIn('"public/css/*.css"', pyproject)
        self.assertIn('"public/images/*.png"', pyproject)
        self.assertIn('"public/js/*.js"', setup_py)
        self.assertIn("recursive-include dcr/public *.css *.js *.png", manifest)
        self.assertIn('DCR_ASSET_VERSION = "20260503-5"', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/sidebar_fix.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/map_warmup.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/css/map.css")', hooks)


class TestMapWorkspaceClientCode(unittest.TestCase):

    def test_map_search_refreshes_after_data_loads(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()
        css = (ROOT / "dcr/public/css/map.css").read_text()

        self.assertIn("window._dcrMapRefreshSearch = refreshSearch", setup_code)
        self.assertIn("if (window._dcrMapRefreshSearch) window._dcrMapRefreshSearch()", setup_code)
        self.assertIn("function scheduleRefresh(resetActive)", setup_code)
        self.assertIn("input.addEventListener('input'", setup_code)
        self.assertIn("input.addEventListener('keyup'", setup_code)
        self.assertIn("input.addEventListener('paste'", setup_code)
        self.assertIn("setTimeout(function() { scheduleRefresh(true); }, 0);", setup_code)
        self.assertIn("_searchHydrated = !!(_searchIndex.length)", setup_code)
        self.assertIn("Loading map results", setup_code)
        self.assertIn(".dcr-search { position: absolute", css)
        self.assertIn("z-index: 1000", css)
        self.assertIn("pointer-events: auto", css)
        self.assertIn(".dcr-search__menu.is-open { display: block !important; }", css)

    def test_map_search_closes_after_selecting_result(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()

        self.assertIn("var suppressMenuUntil = 0", setup_code)
        self.assertIn("function selectHit(item)", setup_code)
        self.assertIn("suppressMenuUntil = Date.now() + 6000", setup_code)
        self.assertIn("m.once('moveend', close)", setup_code)
        self.assertIn("selectHit(hits[active])", setup_code)

    def test_map_popup_actions_use_frappe_router(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()

        self.assertIn("function openDeskDoc(doctype, name)", setup_code)
        self.assertIn("frappe.set_route('Form', doctype, name)", setup_code)
        self.assertIn("openDeskDoc('Home Build Request', name)", setup_code)
        self.assertIn("openDeskDoc('Supplier', name)", setup_code)
        self.assertIn("href=\"/app/home-build-request/", setup_code)
        self.assertIn("href=\"/app/supplier/", setup_code)
        self.assertIn("bindPopupActions(p)", setup_code)
        self.assertIn("window.location.href = '/app/' + slug + '/' + encodeURIComponent(name)", setup_code)
        self.assertIn("window.location.href = '/app/' + slug", setup_code)
        self.assertNotIn("window.open('/app/home-build-request/", setup_code)
        self.assertNotIn("window.open('/app/supplier/", setup_code)
        self.assertNotIn("window.location.href = '/desk/'", setup_code)

    def test_map_click_guard_only_queries_existing_layers(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()

        self.assertIn("function renderedClickLayers(map)", setup_code)
        self.assertIn("if (!layers.length) {", setup_code)
        self.assertIn("map.queryRenderedFeatures(e.point, { layers: layers })", setup_code)

    def test_embedded_map_block_uses_shorter_viewport_height(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()

        self.assertIn("var availableHeight = Math.max(360, window.innerHeight - rect.top)", setup_code)
        self.assertIn("var targetHeight = isMapPage ? availableHeight : Math.round(availableHeight * 0.67)", setup_code)
        self.assertIn("container.style.height = targetHeight + 'px'", setup_code)

    def test_dark_legend_checkmark_uses_span_not_native_checkbox(self):
        setup_code = (ROOT / "dcr/setup.py").read_text()
        css = (ROOT / "dcr/public/css/map.css").read_text()

        self.assertIn('<span class="dcr-legend__check', setup_code)
        self.assertNotIn('<input type="checkbox" class="dcr-legend__check"', setup_code)
        self.assertIn(".dcr-legend__check:checked", css)
        self.assertIn(".dcr-legend__check.is-checked::after", css)
        self.assertIn(".dcr-legend__check:checked::after", css)
        self.assertIn(".dcr-legend--dark .dcr-legend__check.is-checked::after", css)
        self.assertIn(".dcr-legend--dark .dcr-legend__check:checked::after", css)


if __name__ == "__main__":
    unittest.main()
