import frappe
from frappe import _
from frappe.model.document import Document


class FactoryAssignment(Document):
    def on_submit(self):
        # Auto-set status to Submitted
        self.db_set("retailer_application_status", "Submitted")
        self.send_retailer_application()

    def send_retailer_application(self):
        """Send retailer application package to factory via Resend."""
        from dcr.api.resend_integration import send_retailer_application_email
        send_retailer_application_email(self)
