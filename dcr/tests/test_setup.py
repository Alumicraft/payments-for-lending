"""Tests for setup helpers that provision DCR custom fields."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


def _map_block_source():
    """The map workspace block's HTML + JS now live in shipped asset files
    (extracted out of setup.py). These tests assert on that content, so read
    both files and concatenate to reproduce the original combined haystack."""
    html = (ROOT / "dcr/public/html/map_block.html").read_text()
    js = (ROOT / "dcr/public/js/map_block.js").read_text()
    return html + "\n" + js


class TestSetupCustomFields(unittest.TestCase):

    @patch("dcr.setup._ensure_workspace_chart")
    @patch("dcr.setup.frappe")
    def test_pending_deals_card_counts_saved_unsubmitted_hbrs(
        self, mock_frappe, mock_ensure_workspace_chart
    ):
        from dcr.setup import ensure_dcr_dashboard_configuration

        mock_frappe.db.exists.side_effect = (
            lambda doctype, name: doctype == "Number Card" and name == "Pending Deals"
        )

        ensure_dcr_dashboard_configuration()

        updates = mock_frappe.db.set_value.call_args.args[2]
        self.assertEqual(updates["document_type"], "Home Build Request")
        self.assertEqual(
            updates["filters_json"],
            '[["Home Build Request", "docstatus", "=", 0]]',
        )
        mock_ensure_workspace_chart.assert_any_call("Accounting", "Repayment Breakdown", 6)
        mock_ensure_workspace_chart.assert_any_call("Deals", "Deal Pipeline by Factory", 12)

    @patch("dcr.setup.frappe")
    def test_hbr_kanban_has_four_fixed_lifecycle_columns(self, mock_frappe):
        from dcr.setup import ensure_hbr_kanban_columns

        board = MagicMock()
        columns = [
            MagicMock(column_name="Pending"),
            MagicMock(column_name="Ordered"),
            MagicMock(column_name="Delivered"),
            MagicMock(column_name="Draft"),
        ]
        for column in columns:
            column.get.side_effect = lambda field, row=column: getattr(row, field)

        def get_board_field(field):
            if field == "filters":
                return None
            return columns

        def clear_board_field(field, value):
            if field == "columns" and value == []:
                columns.clear()

        def append_board_field(field, value):
            column = MagicMock(column_name=value["column_name"])
            column.get.side_effect = lambda name: getattr(column, name)
            columns.append(column)
            return column

        board.get.side_effect = get_board_field
        board.set.side_effect = clear_board_field
        board.append.side_effect = append_board_field
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_all.return_value = ["Home Build Requests"]
        mock_frappe.get_doc.return_value = board

        ensure_hbr_kanban_columns()

        self.assertEqual(
            board.filters,
            '[["Home Build Request", "docstatus", "in", [0, 1]]]',
        )
        self.assertEqual(
            [column.column_name for column in columns],
            ["Draft", "Pending", "Ordered", "Delivered"],
        )
        board.set.assert_called_once_with("columns", [])
        board.save.assert_called_once_with(ignore_permissions=True)
        mock_frappe.clear_document_cache.assert_called_once_with(
            "Kanban Board", "Home Build Requests"
        )

    @patch("dcr.setup.frappe")
    def test_ensure_bank_account_types_creates_ach_link_targets(self, mock_frappe):
        from dcr.setup import ensure_bank_account_types

        inserted = MagicMock()

        def exists(doctype, name):
            if doctype == "DocType":
                return True
            return name == "Savings"

        mock_frappe.db.exists.side_effect = exists
        mock_frappe.get_doc.return_value = inserted

        ensure_bank_account_types()

        payload = mock_frappe.get_doc.call_args.args[0]
        self.assertEqual(payload, {
            "doctype": "Bank Account Type",
            "account_type": "Checking",
        })
        inserted.insert.assert_called_once_with(ignore_permissions=True)

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

    @patch("dcr.setup.frappe")
    def test_ensure_payment_entry_calculated_fields_installs_field_and_disables_legacy_script(
        self, mock_frappe
    ):
        from dcr.setup import ensure_payment_entry_calculated_fields

        field_doc = MagicMock()

        def exists(doctype, filters):
            if doctype == "Custom Field":
                return False
            if doctype == "Client Script":
                return "Payment Entry - Get Outstanding Balance of Reference Invoices"
            return False

        mock_frappe.db.exists.side_effect = exists
        mock_frappe.db.get_value.return_value = 1
        mock_frappe.get_doc.return_value = field_doc

        ensure_payment_entry_calculated_fields()

        payload = mock_frappe.get_doc.call_args.args[0]
        self.assertEqual(payload["dt"], "Payment Entry")
        self.assertEqual(payload["fieldname"], "custom_total_outstanding")
        self.assertEqual(payload["fieldtype"], "Currency")
        self.assertEqual(payload["read_only"], 1)
        field_doc.insert.assert_called_once_with(ignore_permissions=True)
        mock_frappe.db.set_value.assert_called_once_with(
            "Client Script",
            "Payment Entry - Get Outstanding Balance of Reference Invoices",
            "enabled",
            0,
        )

    @patch("dcr.api.lending.frappe")
    @patch("dcr.setup.frappe")
    def test_ensure_loan_application_field_repairs_updates_mapping_and_addresses(
        self, mock_frappe, mock_lending_frappe
    ):
        from dcr.setup import ensure_loan_application_field_repairs

        phone_property = MagicMock()

        def exists(doctype, value):
            if doctype == "Custom Field":
                return "Loan Application-floor_plan"
            if doctype == "Property Setter":
                return False
            return False

        def get_value(doctype, name, fieldname, *args, **kwargs):
            if doctype == "Custom Field":
                return "home_build_request.model_name"
            return None

        mock_frappe.db.exists.side_effect = exists
        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.get_doc.return_value = phone_property
        mock_frappe.get_all.return_value = [{
            "name": "ACC-LOAP-2026-00008",
            "applicant": "Test Homes 3",
            "address_line_1": None,
            "address_line_2": None,
            "city": "Temecula",
            "state": "CA",
            "zip_code": 92592,
            "country": "United States",
        }]

        def lending_get_value(doctype, name, fieldname, *args, **kwargs):
            if doctype == "Customer":
                return "Test Homes 3-Billing"
            if doctype == "Address":
                return {
                    "address_line1": "41888 Arbor Glen",
                    "address_line2": None,
                    "city": "Temecula",
                    "state": "CA",
                    "pincode": 92592,
                    "country": "United States",
                }
            return None

        mock_lending_frappe.db.get_value.side_effect = lending_get_value

        ensure_loan_application_field_repairs()

        mock_frappe.db.set_value.assert_any_call(
            "Custom Field",
            "Loan Application-floor_plan",
            "fetch_from",
            "home_build_request.floor_plan",
        )
        phone_payload = mock_frappe.get_doc.call_args.args[0]
        self.assertEqual(phone_payload["name"], "Loan Application-applicant_phone_number-options")
        self.assertEqual(phone_payload["value"], "country")
        phone_property.insert.assert_called_once_with(ignore_permissions=True)
        mock_frappe.db.set_value.assert_any_call(
            "Loan Application",
            "ACC-LOAP-2026-00008",
            {"address_line_1": "41888 Arbor Glen"},
            update_modified=False,
        )
        mock_frappe.clear_cache.assert_called_once_with(doctype="Loan Application")

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

    @patch("dcr.setup.frappe")
    def test_ensure_loan_demand_offset_order_repairs_stale_company_links(self, mock_frappe):
        from dcr.setup import ensure_loan_demand_offset_order

        order_doc = MagicMock()

        def exists(doctype, name):
            if doctype == "DocType":
                return name == "Loan Demand Offset Order"
            if doctype == "Loan Demand Offset Order":
                return name == "Existing Offset Order"
            return False

        def get_value(doctype, name, fieldname):
            values = {
                "collection_offset_sequence_for_standard_asset": "IP...IP...IP...CCC",
                "collection_offset_sequence_for_sub_standard_asset": "Existing Offset Order",
                "collection_offset_sequence_for_written_off_asset": None,
                "collection_offset_sequence_for_settlement_collection": "",
            }
            return values[fieldname]

        mock_frappe.db.exists.side_effect = exists
        mock_frappe.get_doc.return_value = order_doc
        mock_frappe.get_all.return_value = ["Dealer Capital Resources"]
        mock_frappe.db.has_column.return_value = True
        mock_frappe.db.get_value.side_effect = get_value

        ensure_loan_demand_offset_order()

        payload = mock_frappe.get_doc.call_args.args[0]
        self.assertEqual(payload["doctype"], "Loan Demand Offset Order")
        self.assertEqual(payload["title"], "DCR Standard Loan Demand Offset Order")
        self.assertEqual(
            [row["demand_type"] for row in payload["components"]],
            ["EMI (Principal + Interest)", "Penalty", "Charges", "Principal"],
        )
        order_doc.insert.assert_called_once_with(ignore_permissions=True)
        mock_frappe.db.set_value.assert_called_once_with(
            "Company",
            "Dealer Capital Resources",
            {
                "collection_offset_sequence_for_standard_asset": "DCR Standard Loan Demand Offset Order",
                "collection_offset_sequence_for_written_off_asset": "DCR Standard Loan Demand Offset Order",
                "collection_offset_sequence_for_settlement_collection": "DCR Standard Loan Demand Offset Order",
            },
            update_modified=False,
        )
        mock_frappe.clear_cache.assert_called_once_with(doctype="Company")

    def test_loan_demand_offset_order_repair_runs_as_patch(self):
        patches = (ROOT / "dcr/patches.txt").read_text()
        patch = (ROOT / "dcr/patches/repair_loan_demand_offset_order.py").read_text()

        self.assertIn("dcr.patches.repair_loan_demand_offset_order", patches)
        self.assertIn("ensure_loan_demand_offset_order()", patch)

    @patch("dcr.setup.frappe")
    def test_ensure_lending_accounting_defaults_repairs_dcr_product(self, mock_frappe):
        from dcr.setup import ensure_lending_accounting_defaults

        def exists(doctype, name):
            if doctype == "DocType":
                return name in {"Loan Product", "Account"}
            if doctype == "Account":
                return name in {
                    "10202 - Loans Receivable - DCR",
                    "10201 - Accounts Receivable (NON QBO) - DCR",
                    "40110 - Service/Fee Income - DCR",
                    "50282 - Bad Debt - DCR",
                    "10102 - Chase Checking 8778 (General) - DCR",
                }
            return False

        def get_value(doctype, name, fieldname):
            if doctype == "Account" and fieldname == "account_type":
                return {
                    "10102 - Chase Checking 8778 (General) - DCR": "Bank",
                    "10202 - Loans Receivable - DCR": "",
                    "10201 - Accounts Receivable (NON QBO) - DCR": "",
                }.get(name)
            if doctype == "Loan Product":
                return {
                    "interest_receivable_account": "10102 - Chase Checking 8778 (General) - DCR",
                    "interest_accrued_account": "10202 - Loans Receivable - DCR",
                    "penalty_receivable_account": None,
                    "write_off_account": None,
                }.get(fieldname)
            return None

        mock_frappe.db.exists.side_effect = exists
        mock_frappe.db.get_value.side_effect = get_value
        mock_frappe.db.has_column.return_value = True
        mock_frappe.get_all.return_value = [{"name": "Standard"}]

        ensure_lending_accounting_defaults()

        mock_frappe.db.set_value.assert_any_call(
            "Account",
            "10202 - Loans Receivable - DCR",
            "account_type",
            "Receivable",
            update_modified=False,
        )
        mock_frappe.db.set_value.assert_any_call(
            "Loan Product",
            "Standard",
            unittest.mock.ANY,
            update_modified=False,
        )
        loan_product_updates = [
            call.args[2]
            for call in mock_frappe.db.set_value.call_args_list
            if call.args[:2] == ("Loan Product", "Standard")
        ][0]
        self.assertEqual(
            loan_product_updates["interest_receivable_account"],
            "10202 - Loans Receivable - DCR",
        )
        self.assertEqual(
            loan_product_updates["interest_accrued_account"],
            "40110 - Service/Fee Income - DCR",
        )
        self.assertEqual(loan_product_updates["write_off_account"], "50282 - Bad Debt - DCR")
        mock_frappe.clear_cache.assert_any_call(doctype="Loan Product")

    def test_lending_accounting_repair_runs_as_patch(self):
        patches = (ROOT / "dcr/patches.txt").read_text()
        patch = (ROOT / "dcr/patches/repair_lending_accounting_defaults.py").read_text()

        self.assertIn("dcr.patches.repair_lending_accounting_defaults", patches)
        self.assertIn("ensure_lending_accounting_defaults()", patch)

    def test_loan_demand_hook_backfills_borrower_fields(self):
        hooks = (ROOT / "dcr/hooks.py").read_text()
        override = (ROOT / "dcr/overrides/loan_demand.py").read_text()
        process_override = (ROOT / "dcr/overrides/process_loan_demand.py").read_text()

        self.assertIn('"Loan Demand"', hooks)
        self.assertIn('"validate": "dcr.api.lending.populate_loan_demand_from_loan"', hooks)
        self.assertIn('"before_submit": "dcr.api.lending.populate_loan_demand_from_loan"', hooks)
        self.assertIn('"Loan Demand": "dcr.overrides.loan_demand.CustomLoanDemand"', hooks)
        self.assertIn(
            '"Process Loan Demand": '
            '"dcr.overrides.process_loan_demand.CustomProcessLoanDemand"',
            hooks,
        )
        self.assertIn("populate_loan_demand_from_loan", hooks)
        self.assertIn("def make_gl_entries", override)
        self.assertIn("populate_loan_demand_from_loan(self)", override)
        self.assertIn("create_loan_demand_with_context", process_override)


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
        setup_code = _map_block_source()

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

        self.assertIn("body.dcr-workspace-fullbleed", css)
        self.assertIn("body.dcr-workspace-fullbleed .page-body", css)
        self.assertIn("--dcr-workspace-content-padding: clamp(16px, 1.5vw, 24px)", css)
        self.assertIn("padding-left: var(--dcr-workspace-content-padding, 20px) !important", css)
        self.assertIn("padding-right: var(--dcr-workspace-content-padding, 20px) !important", css)
        self.assertIn('body.dcr-workspace-fullbleed[data-route="Workspaces/Map"] .container.page-body', css)
        self.assertIn("box-sizing: border-box !important", css)
        self.assertNotIn("margin-left: 0 !important", css)
        self.assertNotIn("margin-right: 0 !important", css)
        self.assertIn('body.dcr-workspace-fullbleed[data-route="Workspaces/Map"] .widget.custom-block-widget-box', css)
        self.assertNotIn("body:has(.workspace-body)", css)
        self.assertNotIn("body[data-route^=\"Workspaces/\"]", css)
        self.assertNotIn(".navbar", css)
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
        self.assertIn('"public/html/*.html"', pyproject)
        self.assertIn('"public/images/*.png"', pyproject)
        self.assertIn('"dcr/dashboard_chart_source/*/*.js"', pyproject)
        self.assertIn('"dcr/dashboard_chart_source/*/*.json"', pyproject)
        self.assertIn('"public/js/*.js"', setup_py)
        self.assertIn('"public/html/*.html"', setup_py)
        self.assertIn('"dcr/dashboard_chart_source/*/*.js"', setup_py)
        self.assertIn("recursive-include dcr/public *.css *.js *.html *.png", manifest)
        self.assertIn("recursive-include dcr/dcr/dashboard_chart_source *.json *.js", manifest)
        self.assertIn('DCR_ASSET_VERSION = "20260731-3"', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/sidebar_fix.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/hbr_dashboard_plus_patch_20260525_10.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/loan_list_context_patch_20260525_14.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/map_warmup.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/css/map.css")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/loan_application.js")', hooks)
        self.assertIn('versioned_asset("/assets/dcr/js/home_build_request.js")', hooks)
        self.assertNotIn(
            '"Home Build Request": versioned_doctype_asset("public/js/home_build_request.js")',
            hooks,
        )

    def test_imported_factory_assignments_are_submitted_without_resending_email(self):
        dealer_import = (ROOT / "dcr/api/dealer_import.py").read_text()
        controller = (
            ROOT / "dcr/dcr/doctype/factory_assignment/factory_assignment.py"
        ).read_text()
        setup = (ROOT / "dcr/setup.py").read_text()
        patches = (ROOT / "dcr/patches.txt").read_text()

        self.assertIn("doc.submit()", dealer_import)
        self.assertIn('if self.retailer_application_status == "Approved":', controller)
        self.assertIn("submit_imported_factory_assignments", setup)
        self.assertIn('"retailer_application_status": "Approved"', setup)
        self.assertIn("dcr.patches.submit_imported_factory_assignments", patches)
        self.assertIn("dcr.patches.backfill_submitted_hbr_checklists", patches)

    def test_factory_address_repair_contains_all_missing_factories(self):
        setup = (ROOT / "dcr/setup.py").read_text()

        self.assertIn('"Durango Homes"', setup)
        self.assertIn('"2502 W Durango St"', setup)
        self.assertIn('"Fleetwood Homes"', setup)
        self.assertIn('"3636 N Central Ave"', setup)
        self.assertIn('"Skyline Homes"', setup)
        self.assertIn('"6420 W Allison Rd"', setup)
        self.assertIn('"Champion Home Builders"', setup)
        self.assertIn('"city": "Phoenix"', setup)
        self.assertNotIn('"city": "Riverside"', setup)
        self.assertNotIn('"city": "San Jacinto"', setup)
        self.assertIn("ensure_factory_addresses,", setup)

    def test_dashboard_repair_uses_explicit_pending_status_and_zero_safe_method(self):
        setup = (ROOT / "dcr/setup.py").read_text()
        fixtures = (ROOT / "dcr/fixtures/dashboard_chart.json").read_text()

        self.assertIn('"Pending Deals": {', setup)
        self.assertIn('["Home Build Request", "docstatus", "=", 0]', setup)
        self.assertIn('["Customer", "dealer_agreement_status", "=", "Sent"]', setup)
        self.assertIn('"method": "dcr.api.dashboard.cash_collected_mtd"', setup)
        self.assertIn('"show_full_number": 1', setup)
        self.assertIn('"Repayment Breakdown"', setup)
        self.assertIn('"Deal Pipeline by Factory"', setup)
        self.assertIn('#59ba8b\\",\\"#0289f7', fixtures)

    def test_dashboard_repair_rebuilds_workspace_chart_children(self):
        setup = (ROOT / "dcr/setup.py").read_text()

        self.assertIn('workspace = frappe.get_doc("Workspace", workspace_name)', setup)
        self.assertIn('workspace.append("charts"', setup)
        self.assertIn('"label": chart_name', setup)
        self.assertIn("workspace.save(ignore_permissions=True)", setup)

    def test_ach_bank_accounts_and_authorization_preserve_account_type(self):
        integration = (ROOT / "dcr/api/achq_integration.py").read_text()
        print_format = (
            ROOT
            / "dcr/dcr/print_format/ach_recurring_payment_authorization/"
            / "ach_recurring_payment_authorization.json"
        ).read_text()

        self.assertIn("ba.account_type = account_type", integration)
        self.assertIn('\\"account_type\\"', print_format)
        self.assertIn('_ba.get(\\"account_type\\"', print_format)
        self.assertIn('_ba.get(\\"custom_verification_status\\"', print_format)

    @patch("dcr.setup.frappe")
    def test_workspace_chart_repair_appends_missing_child_row(self, mock_frappe):
        from dcr.setup import _ensure_workspace_chart

        workspace = MagicMock()
        workspace.content = (
            '[{"type":"chart","data":{"chart_name":"Repayment Breakdown","col":6}}]'
        )
        workspace.get.return_value = []
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = workspace

        _ensure_workspace_chart("Accounting", "Repayment Breakdown", 6)

        workspace.append.assert_called_once_with(
            "charts",
            {
                "chart_name": "Repayment Breakdown",
                "label": "Repayment Breakdown",
            },
        )
        workspace.save.assert_called_once_with(ignore_permissions=True)

    def test_hbr_kanban_repair_matches_pending_backend_value(self):
        setup = (ROOT / "dcr/setup.py").read_text()
        lock = (ROOT / "dcr/public/js/hbr_kanban_lock.js").read_text()

        self.assertIn("ensure_hbr_kanban_columns,", setup)
        self.assertIn('board.set("columns", [])', setup)
        self.assertIn('board.append("columns", {"column_name": column_name})', setup)
        self.assertIn('["Home Build Request", "docstatus", "in", [0, 1]]', setup)
        self.assertIn('desired_columns = ["Draft", "Pending", "Ordered", "Delivered"]', setup)
        self.assertIn('board.filters = active_filter', setup)
        self.assertIn("var route = frappe.get_route() || []", lock)
        self.assertIn('data-column-value="Draft"', lock)
        self.assertIn("parent.insertBefore(this, parent.firstElementChild)", lock)
        self.assertIn(".text(__('Pending'))", lock)
        self.assertIn('data-column-value="Pending"', lock)
        self.assertIn("__('Not Ordered')", lock)
        self.assertIn("function append_hbr_number(card)", lock)
        self.assertIn("'.kanban-card-doc'", lock)
        self.assertIn("'.dcr-hbr-number'", lock)
        self.assertIn("appendTo($properties)", lock)


class TestMapWorkspaceClientCode(unittest.TestCase):

    def test_map_search_refreshes_after_data_loads(self):
        setup_code = _map_block_source()
        css = (ROOT / "dcr/public/css/map.css").read_text()

        self.assertIn("window._dcrMapRefreshSearch = refreshSearch", setup_code)
        self.assertIn("function publishSearchState(extra)", setup_code)
        self.assertIn("function notifySearchIndexReady()", setup_code)
        self.assertIn("document.dispatchEvent(new CustomEvent('dcr-map-search-index-ready'", setup_code)
        self.assertIn("document.addEventListener('dcr-map-search-index-ready'", setup_code)
        self.assertIn("var _searchDataLoaded = { homes: false, factories: false }", setup_code)
        self.assertIn("function scheduleRefresh(resetActive)", setup_code)
        self.assertIn("input.addEventListener('input'", setup_code)
        self.assertIn("input.addEventListener('keyup'", setup_code)
        self.assertIn("input.addEventListener('paste'", setup_code)
        self.assertIn("input.addEventListener('compositionend'", setup_code)
        self.assertIn("input.addEventListener('change'", setup_code)
        self.assertIn("input.addEventListener('focusin'", setup_code)
        self.assertIn("input.addEventListener('click'", setup_code)
        self.assertIn("window.requestAnimationFrame(function() {", setup_code)
        self.assertIn("setTimeout(function() { scheduleRefresh(true); }, 0);", setup_code)
        self.assertIn("_searchHydrated = !!(_searchIndex.length || (_searchDataLoaded.homes && _searchDataLoaded.factories))", setup_code)
        self.assertIn("_searchDataLoaded.homes = true", setup_code)
        self.assertIn("_searchDataLoaded.factories = true", setup_code)
        self.assertIn("Loading map results", setup_code)
        self.assertIn(".dcr-search { position: absolute", css)
        self.assertIn("z-index: 1000", css)
        self.assertIn("pointer-events: auto", css)
        self.assertIn(".dcr-search__menu.is-open { display: block !important; }", css)

    def test_map_search_closes_after_selecting_result(self):
        setup_code = _map_block_source()

        self.assertIn("var suppressMenuUntil = 0", setup_code)
        self.assertIn("function selectHit(item)", setup_code)
        self.assertIn("suppressMenuUntil = Date.now() + 6000", setup_code)
        self.assertIn("m.once('moveend', close)", setup_code)
        self.assertIn("selectHit(hits[active])", setup_code)

    def test_map_popup_actions_use_frappe_router(self):
        setup_code = _map_block_source()

        self.assertIn("function openDeskDoc(doctype, name)", setup_code)
        self.assertIn("frappe.set_route('Form', doctype, name)", setup_code)
        self.assertIn("openDeskDoc('Home Build Request', name)", setup_code)
        self.assertIn("openDeskDoc('Supplier', name)", setup_code)
        self.assertIn("href=\"/app/home-build-request/", setup_code)
        self.assertIn("href=\"/app/supplier/", setup_code)
        self.assertIn('target="_top" data-act="open-hbr"', setup_code)
        self.assertIn('target="_top" data-act="open-supplier"', setup_code)
        self.assertIn("bindPopupActions(p)", setup_code)
        self.assertIn("window.location.href = '/app/' + slug + '/' + encodeURIComponent(name)", setup_code)
        self.assertIn("window.location.href = '/app/' + slug", setup_code)
        self.assertNotIn("window.open('/app/home-build-request/", setup_code)
        self.assertNotIn("window.open('/app/supplier/", setup_code)
        self.assertNotIn("window.location.href = '/desk/'", setup_code)

    def test_map_click_guard_only_queries_existing_layers(self):
        setup_code = _map_block_source()

        self.assertIn("function renderedClickLayers(map)", setup_code)
        self.assertIn("if (!layers.length) {", setup_code)
        self.assertIn("map.queryRenderedFeatures(e.point, { layers: layers })", setup_code)

    def test_embedded_map_block_uses_shorter_viewport_height(self):
        setup_code = _map_block_source()

        self.assertIn("var availableHeight = Math.max(360, window.innerHeight - rect.top)", setup_code)
        self.assertIn("var targetHeight = isMapPage ? availableHeight : Math.round(availableHeight * 0.67)", setup_code)
        self.assertIn("container.style.height = targetHeight + 'px'", setup_code)

    def test_dark_legend_checkmark_uses_span_not_native_checkbox(self):
        setup_code = _map_block_source()
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
