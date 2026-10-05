import frappe
from frappe.model.document import Document


class DCRPilotSettings(Document):
    def validate(self):
        if self.enable_status_notifications and not self.pilot_notification_recipient:
            frappe.throw("A controlled pilot recipient is required before enabling status notifications")
