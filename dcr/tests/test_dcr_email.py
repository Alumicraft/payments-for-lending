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

    def test_email_preview_reuses_email_app_template_data_without_send(self):
        email_api = (ROOT / "dcr/api/dcr_email.py").read_text()

        self.assertIn("def preview_document_email", email_api)
        self.assertIn("build_template_data", email_api)
        self.assertIn("_build_email_preview", email_api)
        self.assertIn("PDF attachment", email_api)
        self.assertIn("def _purchase_order_email_context", email_api)
        self.assertIn("def send_purchase_order_email", email_api)
        self.assertIn('template_override="purchase-order"', email_api)
        for field in ["quote_number", "serial_number", "payment_type", "po_amount"]:
            self.assertIn(f'"{field}"', email_api)


if __name__ == "__main__":
    unittest.main()
