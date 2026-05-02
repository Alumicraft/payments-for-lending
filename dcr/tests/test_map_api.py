"""Tests for map API helper functions.

Pure function tests — no DB or Mapbox API dependency.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestParseMapboxResponse(unittest.TestCase):
    """Test the response parser that extracts structured address data."""

    def test_parse_valid_feature(self):
        from dcr.api.map import _parse_mapbox_feature

        feature = {
            "geometry": {"coordinates": [-118.82, 34.14]},
            "properties": {
                "full_address": "123 Main St, Westlake Village, CA 93065",
                "address": "123 Main St",
                "place": "Westlake Village",
                "region": "California",
                "region_code": "CA",
                "postcode": "93065",
            }
        }
        result = _parse_mapbox_feature(feature)
        self.assertEqual(result["address"], "123 Main St")
        self.assertEqual(result["city"], "Westlake Village")
        self.assertEqual(result["state"], "CA")
        self.assertEqual(result["zip"], "93065")
        self.assertAlmostEqual(result["latitude"], 34.14)
        self.assertAlmostEqual(result["longitude"], -118.82)

    def test_parse_missing_fields_returns_empty_strings(self):
        from dcr.api.map import _parse_mapbox_feature

        feature = {
            "geometry": {"coordinates": [-118.0, 34.0]},
            "properties": {
                "full_address": "Unknown",
            }
        }
        result = _parse_mapbox_feature(feature)
        self.assertEqual(result["address"], "")
        self.assertEqual(result["city"], "")
        self.assertEqual(result["state"], "")
        self.assertEqual(result["zip"], "")
        self.assertEqual(result["full_address"], "Unknown")

    def test_parse_empty_feature(self):
        from dcr.api.map import _parse_mapbox_feature

        feature = {"geometry": {"coordinates": [0, 0]}, "properties": {}}
        result = _parse_mapbox_feature(feature)
        self.assertEqual(result["latitude"], 0)
        self.assertEqual(result["longitude"], 0)


class TestAggregateHeatmapData(unittest.TestCase):
    """Test the aggregation logic that groups HBRs by location + space."""

    def test_aggregate_groups_by_coordinates(self):
        from dcr.api.map import _aggregate_locations

        rows = [
            {"community_name": "Oak Forest", "delivery_address": "123 Main",
             "city": "Westlake", "state": "CA", "zip": "93065",
             "latitude": 34.14, "longitude": -118.82},
            {"community_name": "Oak Forest", "delivery_address": "123 Main",
             "city": "Westlake", "state": "CA", "zip": "93065",
             "latitude": 34.14, "longitude": -118.82},
            {"community_name": "Pine Valley", "delivery_address": "456 Oak",
             "city": "Simi", "state": "CA", "zip": "93063",
             "latitude": 34.27, "longitude": -118.78},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 2)

        oak = next(r for r in result if r["community_name"] == "Oak Forest")
        self.assertEqual(oak["hbr_count"], 2)

        pine = next(r for r in result if r["community_name"] == "Pine Valley")
        self.assertEqual(pine["hbr_count"], 1)

    def test_aggregate_empty_list(self):
        from dcr.api.map import _aggregate_locations

        result = _aggregate_locations([])
        self.assertEqual(result, [])

    def test_aggregate_skips_zero_coordinates(self):
        from dcr.api.map import _aggregate_locations

        rows = [
            {"community_name": "No Coords", "delivery_address": "789 Elm",
             "city": "LA", "state": "CA", "zip": "90001",
             "latitude": 0, "longitude": 0},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 0)

    def test_space_number_separates_pins_at_same_address(self):
        """Two homes in the same park at different spaces become two pins."""
        from dcr.api.map import _aggregate_locations

        rows = [
            {"name": "HBR-001", "community_name": "Sunridge",
             "delivery_address": "100 Park Ln", "city": "Phoenix",
             "state": "AZ", "zip": "85001", "space_number": "12",
             "latitude": 33.4484, "longitude": -112.074},
            {"name": "HBR-002", "community_name": "Sunridge",
             "delivery_address": "100 Park Ln", "city": "Phoenix",
             "state": "AZ", "zip": "85001", "space_number": "14",
             "latitude": 33.4484, "longitude": -112.074},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 2)
        spaces = sorted(r["space_number"] for r in result)
        self.assertEqual(spaces, ["12", "14"])

    def test_no_space_number_stacks_into_one_pin(self):
        """Same address, both with no space number → stacked."""
        from dcr.api.map import _aggregate_locations

        rows = [
            {"name": "HBR-001", "delivery_address": "1 Private Lane",
             "latitude": 33.0, "longitude": -112.0},
            {"name": "HBR-002", "delivery_address": "1 Private Lane",
             "latitude": 33.0, "longitude": -112.0},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["hbr_count"], 2)
        self.assertEqual(len(result[0]["homes"]), 2)

    def test_address_normalization_groups_case_and_whitespace(self):
        """Same address with case/whitespace differences groups together."""
        from dcr.api.map import _aggregate_locations

        rows = [
            {"name": "HBR-001", "delivery_address": "123 Main St",
             "latitude": 34.0, "longitude": -118.0},
            {"name": "HBR-002", "delivery_address": "123  main st",
             "latitude": 34.0, "longitude": -118.0},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["hbr_count"], 2)

    def test_jitter_is_deterministic(self):
        """Same inputs produce the same offsets across calls."""
        from dcr.api.map import _aggregate_locations

        def build():
            return [
                {"name": "HBR-001", "delivery_address": "100 Park",
                 "space_number": "12", "latitude": 33.0, "longitude": -112.0},
                {"name": "HBR-002", "delivery_address": "100 Park",
                 "space_number": "14", "latitude": 33.0, "longitude": -112.0},
            ]
        a = _aggregate_locations(build())
        b = _aggregate_locations(build())
        a_sorted = sorted(a, key=lambda r: r["space_number"])
        b_sorted = sorted(b, key=lambda r: r["space_number"])
        for ra, rb in zip(a_sorted, b_sorted):
            self.assertAlmostEqual(ra["latitude"], rb["latitude"])
            self.assertAlmostEqual(ra["longitude"], rb["longitude"])

    def test_jitter_separates_collisions(self):
        """Two groups at identical coords end up at distinct coords post-jitter."""
        from dcr.api.map import _aggregate_locations

        rows = [
            {"name": "HBR-001", "delivery_address": "100 Park",
             "space_number": "12", "latitude": 33.0, "longitude": -112.0},
            {"name": "HBR-002", "delivery_address": "100 Park",
             "space_number": "14", "latitude": 33.0, "longitude": -112.0},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 2)
        self.assertNotEqual(
            (result[0]["latitude"], result[0]["longitude"]),
            (result[1]["latitude"], result[1]["longitude"]),
        )

    def test_solo_pin_is_not_jittered(self):
        """A single pin at a unique cell stays at its original coords."""
        from dcr.api.map import _aggregate_locations

        rows = [
            {"name": "HBR-001", "delivery_address": "1 Solo St",
             "latitude": 35.0, "longitude": -110.0},
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["latitude"], 35.0)
        self.assertAlmostEqual(result[0]["longitude"], -110.0)


class TestHeatmapQuery(unittest.TestCase):
    """Test heatmap SQL adapts to optional custom fields."""

    @patch("dcr.api.map.frappe")
    def test_missing_purchase_order_hbr_field_does_not_reference_column(self, mock_frappe):
        from dcr.api.map import get_heatmap_data

        mock_frappe.db.has_column.return_value = False
        mock_frappe.db.sql.return_value = []

        get_heatmap_data()

        sql = mock_frappe.db.sql.call_args.args[0]
        self.assertNotIn("custom_home_build_request", sql)

    @patch("dcr.api.map.frappe")
    def test_purchase_order_hbr_field_is_used_when_present(self, mock_frappe):
        from dcr.api.map import get_heatmap_data

        mock_frappe.db.has_column.return_value = True
        mock_frappe.db.sql.return_value = []

        get_heatmap_data()

        sql = mock_frappe.db.sql.call_args.args[0]
        self.assertIn("custom_home_build_request", sql)

    @patch("dcr.api.map.frappe")
    def test_factory_counts_avoid_missing_purchase_order_hbr_field(self, mock_frappe):
        from dcr.api.map import get_factory_locations

        mock_frappe.db.has_column.return_value = False
        mock_frappe.get_all.return_value = [{
            "name": "SUPP-001",
            "supplier_name": "Factory",
            "latitude": 33.0,
            "longitude": -112.0,
        }]
        mock_frappe.db.sql.side_effect = [[], []]

        get_factory_locations()

        sql = mock_frappe.db.sql.call_args_list[0].args[0]
        self.assertNotIn("custom_home_build_request", sql)

    @patch("dcr.api.map.frappe")
    def test_factory_counts_use_purchase_order_hbr_field_when_present(self, mock_frappe):
        from dcr.api.map import get_factory_locations

        mock_frappe.db.has_column.return_value = True
        mock_frappe.get_all.return_value = [{
            "name": "SUPP-001",
            "supplier_name": "Factory",
            "latitude": 33.0,
            "longitude": -112.0,
        }]
        mock_frappe.db.sql.side_effect = [[], []]

        get_factory_locations()

        sql = mock_frappe.db.sql.call_args_list[0].args[0]
        self.assertIn("custom_home_build_request", sql)


class TestStatusDerivation(unittest.TestCase):
    """Status priority: Ordered → Pending → Delivered; Draft folds into Pending."""

    def _row(self, **kwargs):
        base = {
            "name": "HBR-X", "delivery_address": "1 Main St",
            "latitude": 34.0, "longitude": -118.0,
        }
        base.update(kwargs)
        return base

    def test_draft_folds_to_pending(self):
        from dcr.api.map import _aggregate_locations
        rows = [self._row(docstatus=0)]
        self.assertEqual(_aggregate_locations(rows)[0]["status"], "Pending")

    def test_delivered_when_purchase_receipt_exists(self):
        from dcr.api.map import _aggregate_locations
        rows = [self._row(docstatus=1, has_active_po=1, has_pr=1)]
        self.assertEqual(_aggregate_locations(rows)[0]["status"], "Delivered")

    def test_ordered_when_active_po_no_receipt(self):
        from dcr.api.map import _aggregate_locations
        rows = [self._row(docstatus=1, has_active_po=1)]
        self.assertEqual(_aggregate_locations(rows)[0]["status"], "Ordered")

    def test_pending_when_submitted_no_po(self):
        from dcr.api.map import _aggregate_locations
        rows = [self._row(docstatus=1)]
        self.assertEqual(_aggregate_locations(rows)[0]["status"], "Pending")

    def test_stack_status_picks_highest_priority(self):
        """Pin combining Ordered + Delivered colors Ordered (active wins)."""
        from dcr.api.map import _aggregate_locations
        rows = [
            self._row(name="A", docstatus=1, has_active_po=1, has_pr=1),
            self._row(name="B", docstatus=1, has_active_po=1),
        ]
        result = _aggregate_locations(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "Ordered")
        self.assertEqual(len(result[0]["homes"]), 2)


if __name__ == "__main__":
    unittest.main()
