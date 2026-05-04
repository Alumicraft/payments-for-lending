"""Tests for Home Build Request order and loan stage rules."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestHbrOrderStageRules(unittest.TestCase):
    def test_no_submitted_po_is_not_ordered(self):
        from dcr.api.hbr_stage import derive_order_stage

        self.assertEqual(
            derive_order_stage(
                financing_type="Floored",
                has_submitted_po=False,
                has_submitted_pr=False,
                has_closed_loan=False,
            ),
            "Not Ordered",
        )

    def test_submitted_po_without_receipt_is_ordered(self):
        from dcr.api.hbr_stage import derive_order_stage

        self.assertEqual(
            derive_order_stage(
                financing_type="Floored",
                has_submitted_po=True,
                has_submitted_pr=False,
                has_closed_loan=False,
            ),
            "Ordered",
        )

    def test_submitted_receipt_with_active_floored_loan_is_delivered(self):
        from dcr.api.hbr_stage import derive_order_stage

        self.assertEqual(
            derive_order_stage(
                financing_type="Floored",
                has_submitted_po=True,
                has_submitted_pr=True,
                has_closed_loan=False,
            ),
            "Delivered",
        )

    def test_submitted_receipt_with_closed_floored_loan_is_closed(self):
        from dcr.api.hbr_stage import derive_order_stage

        self.assertEqual(
            derive_order_stage(
                financing_type="Floored",
                has_submitted_po=True,
                has_submitted_pr=True,
                has_closed_loan=True,
            ),
            "Closed",
        )

    def test_cash_closed_is_preserved_only_after_delivery(self):
        from dcr.api.hbr_stage import derive_order_stage

        self.assertEqual(
            derive_order_stage(
                financing_type="Cash",
                has_submitted_po=True,
                has_submitted_pr=True,
                has_closed_loan=False,
                current_order_stage="Closed",
            ),
            "Closed",
        )
        self.assertEqual(
            derive_order_stage(
                financing_type="Cash",
                has_submitted_po=True,
                has_submitted_pr=False,
                has_closed_loan=False,
                current_order_stage="Closed",
            ),
            "Ordered",
        )


class TestHbrLoanStageRules(unittest.TestCase):
    def test_cash_deals_are_not_applicable(self):
        from dcr.api.hbr_stage import derive_loan_stage

        self.assertEqual(
            derive_loan_stage(financing_type="Cash"),
            "Not Applicable",
        )

    def test_floored_deal_without_lending_docs_is_not_started(self):
        from dcr.api.hbr_stage import derive_loan_stage

        self.assertEqual(
            derive_loan_stage(financing_type="Floored"),
            "Not Started",
        )

    def test_loan_application_maps_to_applied_or_approved(self):
        from dcr.api.hbr_stage import derive_loan_stage

        self.assertEqual(
            derive_loan_stage(
                financing_type="Floored",
                loan_application_status="Open",
            ),
            "Applied",
        )
        self.assertEqual(
            derive_loan_stage(
                financing_type="Floored",
                loan_application_status="Approved",
            ),
            "Approved",
        )

    def test_loan_status_wins_over_application_status(self):
        from dcr.api.hbr_stage import derive_loan_stage

        self.assertEqual(
            derive_loan_stage(
                financing_type="Floored",
                loan_application_status="Approved",
                loan_status="Disbursed",
            ),
            "Funded",
        )
        self.assertEqual(
            derive_loan_stage(
                financing_type="Floored",
                loan_application_status="Approved",
                loan_status="Active",
            ),
            "Active",
        )
        self.assertEqual(
            derive_loan_stage(
                financing_type="Floored",
                loan_application_status="Approved",
                loan_status="Closed",
            ),
            "Closed",
        )


class TestHbrStageHookRegistration(unittest.TestCase):
    def test_po_pr_and_loan_changes_sync_hbr_stage(self):
        hooks = (ROOT / "dcr/hooks.py").read_text()
        lending = (ROOT / "dcr/api/lending.py").read_text()

        self.assertIn('"Purchase Order"', hooks)
        self.assertIn('"Purchase Receipt"', hooks)
        self.assertIn("dcr.api.hbr_stage.sync_from_doc", hooks)
        self.assertIn("sync_hbr_stages(doc.home_build_request)", lending)


if __name__ == "__main__":
    unittest.main()
