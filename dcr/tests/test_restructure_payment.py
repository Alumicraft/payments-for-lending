"""Saved DCR restructure amounts must describe their generated schedule."""
import ast
import importlib
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


class TrialDocument(dict):
    __getattr__ = dict.get

    def set(self, field, value):
        self[field] = value

    def db_set(self, field, value, **kwargs):
        self[field] = value
        self.writes.append((field, value, kwargs))


class TestRestructurePayment(unittest.TestCase):
    def save_hooks(self, event, doc, schedule_amount=6807, product_type="Interest Only Then Percent Principal"):
        tree = ast.parse((Path(__file__).parents[1] / "hooks.py").read_text())
        events = next(ast.literal_eval(n.value) for n in tree.body
                      if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "doc_events" for t in n.targets))
        target = events.get("Loan Restructure", {}).get(event)
        if not target:
            return
        module_name, function_name = target.rsplit(".", 1)
        module = importlib.import_module(module_name)
        mock = MagicMock()
        mock.db.get_value.side_effect = ["Standard", product_type, schedule_amount]
        mock.throw.side_effect = ValueError
        with patch.object(module, "frappe", mock):
            getattr(module, function_name)(doc, event)

    def document(self, **values):
        doc = TrialDocument(name="RES-A", loan="LOAN-A", docstatus=0,
                            restructure_type="Normal Restructure", new_monthly_repayment_amount=3541, **values)
        doc.writes = []
        return doc

    def test_native_save_quote_matches_first_scheduled_payment(self):
        for event in ("after_insert", "on_update"):
            doc = self.document()
            self.save_hooks(event, doc)
            self.assertEqual(doc.new_monthly_repayment_amount, 6807)
            self.assertEqual(doc.writes, [("new_monthly_repayment_amount", 6807, {"update_modified": False})])
            self.save_hooks(event, doc)
            self.assertEqual(len(doc.writes), 1)

    def test_other_products_and_posted_records_remain_unchanged(self):
        doc = self.document()
        self.save_hooks("on_update", doc, product_type="Amortizing")
        self.assertEqual(doc.new_monthly_repayment_amount, 3541)
        for key, value in (("docstatus", 1), ("docstatus", 2), ("restructure_type", "Pre Payment")):
            doc = self.document()
            doc[key] = value
            self.save_hooks("on_update", doc)
            self.assertEqual(doc.writes, [])

    def test_submission_uses_the_validated_schedule_before_parent_write(self):
        doc = self.document()
        doc["docstatus"] = 1
        self.save_hooks("before_submit", doc)
        self.assertEqual(doc.new_monthly_repayment_amount, 6807)
        self.assertEqual(doc.writes, [])

    def test_missing_schedule_cannot_leave_an_unverified_payment(self):
        with self.assertRaises(ValueError):
            self.save_hooks("on_update", self.document(), schedule_amount=None)
