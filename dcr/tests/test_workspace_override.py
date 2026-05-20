"""Tests for DCR Workspace save override."""

import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[2]


def import_workspace_override():
    desktop = types.ModuleType("frappe.desk.desktop")
    desktop.save_new_widget = MagicMock(return_value=True)

    workspace = types.ModuleType("frappe.desk.doctype.workspace.workspace")
    workspace.is_workspace_manager = MagicMock(return_value=True)

    sys.modules.setdefault("frappe.desk", types.ModuleType("frappe.desk"))
    sys.modules.setdefault("frappe.desk.doctype", types.ModuleType("frappe.desk.doctype"))
    sys.modules.setdefault("frappe.desk.doctype.workspace", types.ModuleType("frappe.desk.doctype.workspace"))
    sys.modules["frappe.desk.desktop"] = desktop
    sys.modules["frappe.desk.doctype.workspace.workspace"] = workspace
    sys.modules.pop("dcr.api.workspace", None)
    return importlib.import_module("dcr.api.workspace")


class TestWorkspaceSaveOverride(unittest.TestCase):

    def test_hooks_override_workspace_save_page(self):
        hooks = (ROOT / "dcr/hooks.py").read_text()

        self.assertIn(
            '"frappe.desk.doctype.workspace.workspace.save_page": "dcr.api.workspace.save_page"',
            hooks,
        )

    def test_strip_orphan_chart_card_blocks_removes_missing_refs(self):
        module = import_workspace_override()
        module.frappe.get_all.side_effect = [["Existing Chart"], ["Existing Card"]]

        blocks = json.dumps([
            {"type": "chart", "data": {"chart_name": "Missing Chart"}},
            {"type": "chart", "data": {"chart_name": "Existing Chart"}},
            {"type": "number_card", "data": {"number_card_name": "Missing Card"}},
            {"type": "number_card", "data": {"number_card_name": "Existing Card"}},
            {"type": "paragraph", "data": {"text": "Keep"}},
        ])
        doc = MagicMock(name="Overview")
        doc.name = "Overview"

        cleaned = json.loads(module._strip_orphan_chart_card_blocks(doc, blocks))

        self.assertEqual(
            cleaned,
            [
                {"type": "chart", "data": {"chart_name": "Existing Chart"}},
                {"type": "number_card", "data": {"number_card_name": "Existing Card"}},
                {"type": "paragraph", "data": {"text": "Keep"}},
            ],
        )
        module.frappe.log_error.assert_called_once()

    def test_public_workspace_manager_gets_save_response(self):
        module = import_workspace_override()
        module.frappe.parse_json.side_effect = lambda value: value
        module.frappe.session.user = "admin@example.com"
        module.frappe.get_all.side_effect = [[], []]

        doc = MagicMock()
        doc.public = 1
        doc.for_user = ""
        doc.type = "Workspace"
        doc.label = "Overview"
        module.frappe.get_doc.return_value = doc

        result = module.save_page("Overview", 1, "{}", "[]")

        self.assertEqual(result, {"name": "Overview", "public": 1, "label": "Overview"})
        module.save_new_widget.assert_called_once_with(doc, "Overview", "[]", "{}")
        module.frappe.clear_document_cache.assert_called_once_with("Workspace", "Overview")
        module.frappe.clear_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
