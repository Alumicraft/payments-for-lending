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
        self.assertIn('"Loan Repayment"', hooks)
        self.assertIn("dcr.api.hbr_stage.sync_from_doc", hooks)
        self.assertIn('"on_update_after_submit": "dcr.api.hbr_stage.sync_from_doc"', hooks)
        self.assertIn("sync_hbr_stages(doc.home_build_request)", lending)

    def test_loan_repayment_resolves_hbr_from_against_loan(self):
        hbr_stage = (ROOT / "dcr/api/hbr_stage.py").read_text()

        self.assertIn('if doc.doctype == "Loan Repayment"', hbr_stage)
        self.assertIn('doc.get("against_loan")', hbr_stage)
        self.assertIn('frappe.db.get_value("Loan", loan_name, "home_build_request")', hbr_stage)


class TestHbrStageSetup(unittest.TestCase):
    def test_cash_loan_stage_option_is_preserved_after_migrate(self):
        setup = (ROOT / "dcr/setup.py").read_text()

        self.assertIn("ensure_hbr_stage_field_options()", setup)
        self.assertIn("sync_existing_hbr_stage_fields()", setup)
        self.assertIn("custom_loan_stage", setup)
        self.assertIn("Not Applicable\\nNot Started\\nApplied", setup)

    def test_stage_fields_are_read_only_derived_fields_after_migrate(self):
        setup = (ROOT / "dcr/setup.py").read_text()

        self.assertIn('updates["read_only"] = 1', setup)
        self.assertIn('updates["allow_on_submit"] = 0', setup)
        self.assertIn('frappe.db.set_value("Custom Field", custom_field, updates)', setup)

    def test_migrate_patch_backfills_existing_hbr_stages(self):
        patches = (ROOT / "dcr/patches.txt").read_text()
        patch = (ROOT / "dcr/patches/sync_hbr_stage_fields.py").read_text()

        self.assertIn("dcr.patches.sync_hbr_stage_fields", patches)
        self.assertIn("ensure_hbr_stage_field_options()", patch)
        self.assertIn("sync_hbr_stages(hbr_name)", patch)

    def test_submit_status_is_backfilled_and_maintained(self):
        controller = (
            ROOT / "dcr/dcr/doctype/home_build_request/home_build_request.py"
        ).read_text()
        patches = (ROOT / "dcr/patches.txt").read_text()
        patch = (ROOT / "dcr/patches/sync_hbr_submit_status.py").read_text()

        self.assertIn('self.db_set("status", "Submitted")', controller)
        self.assertIn("dcr.patches.sync_hbr_submit_status", patches)
        self.assertIn("WHERE docstatus = 1", patch)


if __name__ == "__main__":
    unittest.main()
