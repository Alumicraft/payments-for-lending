import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class DCRPilotSettings(Document):
    def validate(self):
        if not self.enable_status_notifications:
            self.pilot_notifications_from = None
            return
        if self.enable_status_notifications and not self.pilot_notification_recipient:
            frappe.throw("A controlled pilot recipient is required before enabling status notifications")
        before = self.get_doc_before_save()
        self.pilot_notifications_from = (
            before.get('pilot_notifications_from') if before and before.enable_status_notifications
            and before.get('pilot_notifications_from') else now_datetime()
        )
