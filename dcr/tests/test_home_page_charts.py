"""Workspace layout provisioning tests without a running Frappe site."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class Row(SimpleNamespace):
    def get(self, key):
        return getattr(self, key, None)


class Workspace:
    def __init__(self, name, content=None, charts=None):
        self.name = name
        self.content = json.dumps(content or [])
        self.charts = [Row(**row) for row in charts or []]
        self.save = MagicMock()

    def get(self, field):
        return getattr(self, field, None)

    def append(self, field, values):
        getattr(self, field).append(Row(**values))


class TestHomePageChartProvisioning(unittest.TestCase):
    def _site(self, frappe):
        from dcr.setup import DCR_HOME_PAGE_CHARTS

        self.workspaces = {name: Workspace(name) for name in ["Overview", *DCR_HOME_PAGE_CHARTS]}
        self.chart_names = {name for charts in DCR_HOME_PAGE_CHARTS.values() for name, _ in charts}
        frappe.db.exists.side_effect = lambda doctype, name: (
            name in self.workspaces if doctype == "Workspace" else name in self.chart_names
        )
        frappe.get_doc.side_effect = lambda doctype, name: self.workspaces[name]

    @patch("dcr.setup.frappe")
    def test_places_all_shipped_charts_on_home_pages_and_sectioned_overview(self, frappe):
        from dcr.setup import DCR_HOME_PAGE_CHARTS, ensure_dcr_home_page_charts

        self._site(frappe)
        ensure_dcr_home_page_charts()

        for name, charts in DCR_HOME_PAGE_CHARTS.items():
            self.assertEqual(
                {row.chart_name for row in self.workspaces[name].charts},
                {chart for chart, col in charts},
            )
            self.assertEqual(
                {block["data"]["chart_name"] for block in json.loads(self.workspaces[name].content)},
                {chart for chart, col in charts},
            )
        overview = json.loads(self.workspaces["Overview"].content)
        headings = [block["data"]["text"] for block in overview if block["type"] == "header"]
        self.assertEqual(headings, ["Deals", "Accounting", "Contacts", "Access"])
        self.assertEqual({row.chart_name for row in self.workspaces["Overview"].charts}, self.chart_names)
        section = None
        for block in overview:
            if block["type"] == "header":
                section = block["data"]["text"]
            else:
                self.assertIn(block["data"]["chart_name"], dict(DCR_HOME_PAGE_CHARTS[section]))

    @patch("dcr.setup.frappe")
    def test_repeated_setup_does_not_duplicate_charts_or_write_unchanged_pages(self, frappe):
        from dcr.setup import ensure_dcr_home_page_charts

        self._site(frappe)
        ensure_dcr_home_page_charts()
        content_before = {name: doc.content for name, doc in self.workspaces.items()}
        row_counts = {name: len(doc.charts) for name, doc in self.workspaces.items()}
        save_counts = {name: doc.save.call_count for name, doc in self.workspaces.items()}
        ensure_dcr_home_page_charts()

        for name, doc in self.workspaces.items():
            self.assertEqual(doc.content, content_before[name])
            self.assertEqual(len(doc.charts), row_counts[name])
            self.assertEqual(doc.save.call_count, save_counts[name])

    @patch("dcr.setup.frappe")
    def test_site_configured_contacts_chart_with_custom_label_is_repaired_and_mirrored(self, frappe):
        from dcr.setup import ensure_dcr_home_page_charts

        self._site(frappe)
        self.chart_names.add("Dealer Activity")
        contacts = self.workspaces["Contacts"]
        contacts.append("charts", {"chart_name": "Dealer Activity", "label": "Our dealers"})
        ensure_dcr_home_page_charts()

        blocks = json.loads(contacts.content)
        self.assertIn("Our dealers", [block["data"]["chart_name"] for block in blocks])
        overview = json.loads(self.workspaces["Overview"].content)
        self.assertIn("Contacts", [block["data"]["text"] for block in overview if block["type"] == "header"])
        self.assertIn("Dealer Activity", [row.chart_name for row in self.workspaces["Overview"].charts])

    @patch("dcr.setup.frappe")
    def test_chart_widget_uses_its_child_row_label(self, frappe):
        from dcr.setup import _ensure_workspace_chart

        self._site(frappe)
        workspace = self.workspaces["Deals"]
        workspace.append("charts", {"chart_name": "New Deals by Type", "label": "Our deals"})
        workspace.content = json.dumps([{
            "type": "chart", "data": {"chart_name": "New Deals by Type", "col": 6},
        }])
        _ensure_workspace_chart("Deals", "New Deals by Type", 6)
        self.assertEqual(json.loads(workspace.content)[0]["data"]["chart_name"], "Our deals")
        self.assertEqual(len(workspace.charts), 1)
        workspace.save.assert_called_once_with(ignore_permissions=True)

    def test_contacts_chart_uses_native_count_of_dealer_customers(self):
        root = Path(__file__).resolve().parents[2]
        charts = json.loads((root / "dcr/fixtures/dashboard_chart.json").read_text())
        contacts = next(chart for chart in charts if chart["name"] == "New Dealers by Month")
        self.assertEqual(contacts["chart_type"], "Count")
        self.assertEqual(contacts["document_type"], "Customer")
        self.assertEqual(contacts["based_on"], "creation")
        self.assertEqual(json.loads(contacts["filters_json"]), [
            ["Customer", "customer_group", "=", "Dealer"],
            ["Customer", "disabled", "=", 0],
        ])

    @patch("dcr.setup.frappe")
    def test_missing_charts_do_not_create_broken_references(self, frappe):
        from dcr.setup import ensure_dcr_home_page_charts

        self._site(frappe)
        self.chart_names.clear()
        ensure_dcr_home_page_charts()
        for doc in self.workspaces.values():
            self.assertEqual(json.loads(doc.content), [])
            self.assertEqual(doc.charts, [])
            doc.save.assert_not_called()

    @patch("dcr.setup.frappe")
    def test_invalid_overview_is_preserved_and_failure_is_visible(self, frappe):
        from dcr.setup import ensure_dcr_home_page_charts

        self._site(frappe)
        overview = self.workspaces["Overview"]
        overview.content = '{"not":"a list"}'
        with self.assertRaisesRegex(ValueError, "Overview"):
            ensure_dcr_home_page_charts()
        self.assertEqual(overview.content, '{"not":"a list"}')
        overview.save.assert_not_called()


class TestOverviewChartGrouping(unittest.TestCase):
    def test_reuses_headings_moves_known_charts_and_preserves_other_widgets(self):
        from dcr.setup import _group_overview_charts

        card = {"id": "card", "type": "number_card", "data": {"number_card_name": "Pending Deals"}}
        map_block = {"id": "map", "type": "custom_block", "data": {"custom_block_name": "Map"}}
        unrelated_chart = {"type": "chart", "data": {"chart_name": "Other Chart", "col": 6}}
        content = [
            {"id": "old-chart", "type": "chart", "data": {"chart_name": "Old Label", "col": 12}},
            {"id": "deals", "type": "header", "data": {"text": "<b>Deals</b>", "col": 12}},
            card, map_block, unrelated_chart,
            {"type": "chart", "data": {"chart_name": "New Deals by Type", "col": 6}},
        ]
        sections = {"Deals": {"New Deals by Type": 6}, "Accounting": {"Past-Due Aging": 6}}
        result = _group_overview_charts(content, sections, {"Old Label": "New Deals by Type"})
        self.assertIn(card, result)
        self.assertIn(map_block, result)
        self.assertIn(unrelated_chart, result)
        self.assertEqual(len([block for block in result if block["type"] == "header"]), 2)
        self.assertEqual(len([block for block in result if block["type"] == "chart"]), 3)
        self.assertEqual(_group_overview_charts(result, sections), result)


if __name__ == "__main__":
    unittest.main()
