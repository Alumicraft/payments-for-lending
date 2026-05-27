"""Tests for DCR dashboard chart data methods.

Pure unit tests with frappe mocked via conftest — no bench required. Verify
the shape of the return value (labels + datasets), correct month alignment,
and that the past-due aging chart emits all four buckets even when the DB
has no past-due rows.

conftest.py provides real implementations of frappe.utils.{nowdate, getdate,
get_first_day, add_months}, frozen to nowdate() = "2026-06-15". Per-test SQL
results are injected with patch.object(dashboard.frappe.db, "sql", ...).
"""

from __future__ import annotations

import datetime
import unittest
from unittest.mock import patch

import dcr.api.dashboard as dashboard


class FakeRow(dict):
    """Mimics frappe._dict: supports both r.attr and r['key'] access.

    Real frappe.db.sql(as_dict=True) returns frappe._dict rows. Production
    code in dashboard.py uses attribute access (`r.bucket`), so the test
    stubs must do the same.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class TestLastNMonths(unittest.TestCase):
    def test_returns_n_months_oldest_first(self):
        months = dashboard._last_n_months(12)
        self.assertEqual(len(months), 12)
        # All first-of-month
        self.assertTrue(all(m.day == 1 for m in months))
        # Oldest first
        self.assertTrue(all(months[i] < months[i + 1] for i in range(len(months) - 1)))
        # Last is the current month (frozen at 2026-06-15 in conftest)
        self.assertEqual(months[-1], datetime.date(2026, 6, 1))
        self.assertEqual(months[0], datetime.date(2025, 7, 1))


class TestPastDueAging(unittest.TestCase):
    def test_returns_all_four_buckets_with_no_data(self):
        with patch.object(dashboard.frappe.db, "sql", return_value=[]):
            result = dashboard.past_due_aging()

        self.assertEqual(result["labels"], ["1-30", "31-60", "61-90", "90+"])
        self.assertEqual(len(result["datasets"]), 1)
        self.assertEqual(result["datasets"][0]["values"], [0, 0, 0, 0])

    def test_buckets_populate_from_sql_rows(self):
        rows = [
            FakeRow(bucket="1-30", total=1500.0),
            FakeRow(bucket="31-60", total=800.0),
            FakeRow(bucket="90+", total=4200.0),
        ]
        with patch.object(dashboard.frappe.db, "sql", return_value=rows):
            result = dashboard.past_due_aging()

        # Missing 61-90 bucket renders as 0, ordering preserved
        self.assertEqual(result["datasets"][0]["values"], [1500.0, 800.0, 0, 4200.0])

    def test_dataset_is_named_past_due_amount(self):
        with patch.object(dashboard.frappe.db, "sql", return_value=[]):
            result = dashboard.past_due_aging()
        self.assertEqual(result["datasets"][0]["name"], "Past-Due Amount")


class TestInflowsVsOutflows(unittest.TestCase):
    def test_returns_twelve_labels_and_two_datasets(self):
        with patch.object(dashboard.frappe.db, "sql", return_value=[]):
            result = dashboard.inflows_vs_outflows()

        self.assertEqual(len(result["labels"]), 12)
        self.assertEqual(len(result["datasets"]), 2)
        self.assertEqual(
            [d["name"] for d in result["datasets"]],
            ["Principal Advanced", "Payments Received"],
        )
        # All zeros when no data
        for dataset in result["datasets"]:
            self.assertEqual(len(dataset["values"]), 12)
            self.assertEqual(dataset["values"], [0] * 12)

    def test_rows_align_to_correct_month_slots(self):
        # Two SQL calls — first is outflows, second is inflows
        outflow_rows = [FakeRow(m="2026-06-01", total=50000.0)]
        inflow_rows = [FakeRow(m="2026-05-01", total=12000.0)]

        with patch.object(dashboard.frappe.db, "sql", side_effect=[outflow_rows, inflow_rows]):
            result = dashboard.inflows_vs_outflows()

        # Last slot (index 11) is June 2026 in the frozen-date world
        self.assertEqual(result["datasets"][0]["values"][11], 50000.0)
        # Second-to-last slot (index 10) is May 2026
        self.assertEqual(result["datasets"][1]["values"][10], 12000.0)
        # All other slots are zero
        self.assertEqual(sum(result["datasets"][0]["values"]), 50000.0)
        self.assertEqual(sum(result["datasets"][1]["values"]), 12000.0)


class TestNewDealsByType(unittest.TestCase):
    def test_returns_twelve_labels_and_cash_floored_datasets(self):
        with patch.object(dashboard.frappe.db, "sql", return_value=[]):
            result = dashboard.new_deals_by_type()

        self.assertEqual(len(result["labels"]), 12)
        self.assertEqual([d["name"] for d in result["datasets"]], ["Cash", "Floored"])
        for dataset in result["datasets"]:
            self.assertEqual(dataset["values"], [0] * 12)

    def test_splits_rows_by_financing_type(self):
        rows = [
            FakeRow(m="2026-06-01", financing_type="Cash", n=3),
            FakeRow(m="2026-06-01", financing_type="Floored", n=7),
            FakeRow(m="2026-05-01", financing_type="Floored", n=4),
        ]
        with patch.object(dashboard.frappe.db, "sql", return_value=rows):
            result = dashboard.new_deals_by_type()

        cash_values = result["datasets"][0]["values"]
        floored_values = result["datasets"][1]["values"]

        # June 2026 (index 11)
        self.assertEqual(cash_values[11], 3)
        self.assertEqual(floored_values[11], 7)
        # May 2026 (index 10)
        self.assertEqual(cash_values[10], 0)
        self.assertEqual(floored_values[10], 4)

    def test_ignores_unknown_financing_types(self):
        rows = [
            FakeRow(m="2026-06-01", financing_type="Cash", n=2),
            FakeRow(m="2026-06-01", financing_type="Mystery", n=99),
        ]
        with patch.object(dashboard.frappe.db, "sql", return_value=rows):
            result = dashboard.new_deals_by_type()

        # Unknown types are silently dropped — Cash count is unaffected
        self.assertEqual(result["datasets"][0]["values"][11], 2)
        # Mystery did not bleed into Floored
        self.assertEqual(result["datasets"][1]["values"][11], 0)


if __name__ == "__main__":
    unittest.main()
