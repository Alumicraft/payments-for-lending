"""Tests for setup helpers that provision DCR custom fields."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


class TestSetupCustomFields(unittest.TestCase):

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
        self.assertIn(".dcr-legend__check:checked::after", css)
        self.assertIn(".dcr-legend--dark .dcr-legend__check:checked::after", css)


if __name__ == "__main__":
    unittest.main()
