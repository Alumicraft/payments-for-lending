"""Tests for get_required_docs() branch logic.

This is the core intake logic — wrong checklist means wrong docs collected.
Pure function, no database dependency.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from dcr.dcr.doctype.home_build_request.home_build_request import get_required_docs, DOC_REQUIREMENTS


class TestGetRequiredDocs(unittest.TestCase):

    # ------------------------------------------------------------------
    # Spec orders
    # ------------------------------------------------------------------

    def test_spec_cash_park(self):
        docs = get_required_docs("Spec", "Cash", "Park")
        self.assertIn("Spec Info Sheet", docs)
        self.assertIn("Storage Agreement", docs)
        self.assertIn("Park Agreement", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertEqual(len(docs), 5)

    def test_spec_cash_private(self):
        docs = get_required_docs("Spec", "Cash", "Private Property")
        self.assertIn("Spec Info Sheet", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertIn("50% Deposit Proof", docs)
        self.assertEqual(len(docs), 4)

    def test_spec_floored_park(self):
        docs = get_required_docs("Spec", "Floored", "Park")
        self.assertIn("Spec Info Sheet", docs)
        self.assertIn("Storage Agreement", docs)
        self.assertIn("Park Agreement", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertEqual(len(docs), 5)

    def test_spec_floored_private(self):
        docs = get_required_docs("Spec", "Floored", "Private Property")
        self.assertIn("Spec Info Sheet", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertIn("50% Deposit Proof", docs)
        self.assertEqual(len(docs), 4)

    # ------------------------------------------------------------------
    # Customer Sold orders
    # ------------------------------------------------------------------

    def test_customer_sold_cash_park(self):
        docs = get_required_docs("Customer Sold", "Cash", "Park")
        self.assertIn("Retail Sold Info Sheet", docs)
        self.assertIn("Purchase Contract", docs)
        self.assertIn("Escrow Proof", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertIn("Loan Approval", docs)
        self.assertIn("Park Approval", docs)
        self.assertIn("Insurance", docs)
        self.assertEqual(len(docs), 8)

    def test_customer_sold_cash_private(self):
        docs = get_required_docs("Customer Sold", "Cash", "Private Property")
        self.assertIn("Cash Private Info Sheet", docs)
        self.assertIn("Purchase Contract", docs)
        self.assertIn("Escrow Proof", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("50% Deposit Proof", docs)
        self.assertEqual(len(docs), 5)

    def test_customer_sold_floored_park(self):
        docs = get_required_docs("Customer Sold", "Floored", "Park")
        self.assertIn("Retail Sold Info Sheet", docs)
        self.assertIn("Purchase Contract", docs)
        self.assertIn("Escrow Proof", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertIn("Loan Approval", docs)
        self.assertIn("Park Approval", docs)
        self.assertIn("Insurance", docs)
        self.assertEqual(len(docs), 8)

    def test_customer_sold_floored_private(self):
        docs = get_required_docs("Customer Sold", "Floored", "Private Property")
        self.assertIn("Retail Sold Info Sheet", docs)
        self.assertIn("Purchase Contract", docs)
        self.assertIn("Escrow Proof", docs)
        self.assertIn("Factory Quote", docs)
        self.assertIn("Plot Plan", docs)
        self.assertEqual(len(docs), 5)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_unknown_combination_returns_empty(self):
        docs = get_required_docs("Unknown", "Unknown", "Unknown")
        self.assertEqual(docs, [])

    def test_empty_strings_return_empty(self):
        docs = get_required_docs("", "", "")
        self.assertEqual(docs, [])

    def test_all_combinations_covered(self):
        """Every valid combo of home_type x financing_type x property_type has docs."""
        home_types = ["Spec", "Customer Sold"]
        financing_types = ["Cash", "Floored"]
        property_types = ["Park", "Private Property"]

        for ht in home_types:
            for ft in financing_types:
                for pt in property_types:
                    docs = get_required_docs(ht, ft, pt)
                    self.assertGreater(
                        len(docs), 0,
                        f"No docs returned for ({ht}, {ft}, {pt})"
                    )

    def test_factory_quote_always_required(self):
        """Factory Quote should appear in every valid combination."""
        for key, docs in DOC_REQUIREMENTS.items():
            self.assertIn("Factory Quote", docs, f"Missing Factory Quote for {key}")


class TestHomeBuildRequestAttachmentSync(unittest.TestCase):

    @patch("dcr.dcr.doctype.home_build_request.home_build_request.frappe")
    def test_sync_links_current_checklist_files_to_hbr(self, mock_frappe):
        from dcr.dcr.doctype.home_build_request.home_build_request import sync_linked_files

        doc = SimpleNamespace(
            doctype="Home Build Request",
            name="HBR-001",
            doc_checklist=[
                SimpleNamespace(attachment="/files/factory-quote.pdf"),
                SimpleNamespace(attachment="/files/plot-plan.pdf"),
            ],
        )
        file_doc = MagicMock()
        mock_frappe.db.exists.return_value = False
        mock_frappe.db.get_value.return_value = "FILE-001"
        mock_frappe.get_doc.return_value = file_doc

        sync_linked_files(doc, ["doc_checklist"])

        self.assertEqual(mock_frappe.db.get_value.call_count, 2)
        file_doc.db_set.assert_any_call(
            {
                "attached_to_doctype": "Home Build Request",
                "attached_to_name": "HBR-001",
                "attached_to_field": "doc_checklist",
            },
            update_modified=False,
        )
        self.assertEqual(file_doc.db_set.call_count, 2)

    @patch("dcr.dcr.doctype.home_build_request.home_build_request.frappe")
    def test_sync_skips_files_already_linked_to_hbr(self, mock_frappe):
        from dcr.dcr.doctype.home_build_request.home_build_request import sync_linked_files

        doc = SimpleNamespace(
            doctype="Home Build Request",
            name="HBR-001",
            doc_checklist=[SimpleNamespace(attachment="/files/factory-quote-v2.pdf")],
        )
        file_doc = MagicMock()
        file_doc.attached_to_doctype = "Home Build Request"
        file_doc.attached_to_name = "HBR-001"
        file_doc.attached_to_field = "doc_checklist"
        mock_frappe.db.get_value.return_value = "FILE-002"
        mock_frappe.get_doc.return_value = file_doc

        sync_linked_files(doc, ["doc_checklist"])

        file_doc.db_set.assert_not_called()

    @patch("dcr.dcr.doctype.home_build_request.home_build_request.frappe")
    def test_sync_detaches_stale_checklist_file_links_only(self, mock_frappe):
        from dcr.dcr.doctype.home_build_request.home_build_request import sync_linked_files

        doc = SimpleNamespace(
            doctype="Home Build Request",
            name="HBR-001",
            doc_checklist=[SimpleNamespace(attachment="/files/factory-quote-v2.pdf")],
        )
        current_file = MagicMock()
        current_file.attached_to_doctype = "Document Checklist"
        current_file.attached_to_name = "row-2"
        current_file.attached_to_field = "attachment"
        stale_file = MagicMock()
        mock_frappe.db.exists.return_value = False
        mock_frappe.db.get_value.return_value = "FILE-002"
        mock_frappe.get_doc.side_effect = [stale_file, current_file]
        mock_frappe.get_all.return_value = [
            {"name": "FILE-001", "file_url": "/files/factory-quote-v1.pdf"},
        ]

        sync_linked_files(doc, ["doc_checklist"])

        stale_file.db_set.assert_called_once_with(
            {
                "attached_to_doctype": None,
                "attached_to_name": None,
                "attached_to_field": None,
            },
            update_modified=False,
        )
        current_file.db_set.assert_called_once_with(
            {
                "attached_to_doctype": "Home Build Request",
                "attached_to_name": "HBR-001",
                "attached_to_field": "doc_checklist",
            },
            update_modified=False,
        )
        self.assertEqual(
            mock_frappe.get_all.call_args.kwargs["filters"]["attached_to_field"],
            ["in", ["doc_checklist"]],
        )


if __name__ == "__main__":
    unittest.main()
