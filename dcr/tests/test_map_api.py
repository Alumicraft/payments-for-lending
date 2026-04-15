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
    """Test the aggregation logic that groups HBRs by location."""

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


if __name__ == "__main__":
    unittest.main()
