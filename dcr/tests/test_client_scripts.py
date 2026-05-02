"""Static regression checks for Frappe client scripts.

There is no JavaScript test harness in this repo, so these tests pin critical
workflow guards in the client scripts.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestHomeBuildRequestClientScript(unittest.TestCase):

    def test_cash_deals_do_not_show_create_loan_application_button(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("if (frm.doc.financing_type === 'Floored')", script)
        self.assertNotIn("if (frm.doc.financing_type !== 'Floored') return;", script)


class TestLoanClientScript(unittest.TestCase):

    def test_disbursement_notice_passes_hbr_not_serial_number(self):
        script = (ROOT / "dcr/public/js/loan.js").read_text()

        self.assertIn("home_build_request: frm.doc.home_build_request || ''", script)
        self.assertNotIn("home_build_request: frm.doc.home_serial_no || ''", script)


if __name__ == "__main__":
    unittest.main()
