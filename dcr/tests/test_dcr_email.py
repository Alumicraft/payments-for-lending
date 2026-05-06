import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestDcrEmailFormatting(unittest.TestCase):
    def test_disbursement_email_formats_amount_before_sending(self):
        email_api = (ROOT / "dcr/api/dcr_email.py").read_text()

        self.assertIn("def _format_currency_amount", email_api)
        self.assertIn("formatted_amount = _format_currency_amount(amount)", email_api)
        self.assertIn('subject=f"Loan Advance Disbursed — ${formatted_amount}"', email_api)
        self.assertIn('"amount": formatted_amount', email_api)


if __name__ == "__main__":
    unittest.main()
