"""Tests for get_required_docs() branch logic.

This is the core intake logic — wrong checklist means wrong docs collected.
Pure function, no database dependency.
"""

import unittest
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


if __name__ == "__main__":
    unittest.main()
