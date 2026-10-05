"""Durable deal-transition notices, delivered only to a configured pilot mailbox."""
import hashlib
from html import escape
import frappe
from frappe.utils import get_url
from dcr.api.notification_queue import queue_notification

EVENT_FIELDS = {
    "custom_portal_status": "Review status",
    "custom_order_stage": "Order stage",
    "custom_loan_stage": "Loan stage",
    "in_storage": "Storage",
}


def record_transition(hbr, field, old, new, revision=None):
    if field not in EVENT_FIELDS or old == new or (not new and field != "in_storage") or frappe.flags.in_migrate:
        return
    if field == "custom_portal_status" and new == "Draft":
        return
    settings = frappe.get_single("DCR Pilot Settings")
    staff = field == "custom_portal_status" and new == "Submitted for Review"
    audience = "Staff" if staff else "Dealer"
    intended = settings.staff_notification_recipient if staff else frappe.db.get_value("Customer", hbr.customer, "email_id")
    revision = revision or hbr.modified
    key = hashlib.sha256(f"{hbr.name}|{field}|{old}|{new}|{revision}".encode()).hexdigest()
    name = f"DCR-NOTICE-{key}"
    if frappe.db.exists("DCR Status Notice", name):
        return
    value = ("In Storage" if new else "Not In Storage") if field == "in_storage" else str(new)
    subject = f"{hbr.name}: {EVENT_FIELDS[field]} — {value}"
    url = get_url(f"/app/home-build-request/{hbr.name}" if staff else "/portal")
    message = f"<p>{escape(hbr.name)}: {escape(EVENT_FIELDS[field])} changed from {escape(str(old or 'Not set'))} to <strong>{escape(value)}</strong>.</p><p><a href='{escape(url, quote=True)}'>Open {'deal' if staff else 'dealer portal'}</a></p>"
    frappe.db.savepoint("dcr_notice_insert")
    try:
        frappe.get_doc(dict(doctype="DCR Status Notice", name=name, event_key=name, home_build_request=hbr.name,
            customer=hbr.customer, event=f"{field}: {old} → {new}", audience=audience,
            recipient=intended, subject=subject, message=message, status="Recorded")).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point="dcr_notice_insert")


def capture_hbr_changes(doc, method=None):
    before = doc.get_doc_before_save()
    if not before:
        return
    for field in EVENT_FIELDS:
        record_transition(doc, field, before.get(field), doc.get(field))


def queue_pilot_notices():
    settings = frappe.get_single("DCR Pilot Settings")
    if not settings.enable_status_notifications or not settings.pilot_notification_recipient:
        return
    names = frappe.get_all("DCR Status Notice", filters={"status": "Recorded"}, pluck="name", limit_page_length=100)
    for name in names:
        savepoint = "dcr_notice"
        frappe.db.savepoint(savepoint)
        try:
            frappe.db.get_value("DCR Status Notice", name, "name", for_update=True)
            notice = frappe.get_doc("DCR Status Notice", name)
            if notice.status != "Recorded":
                continue
            # Email Queue creation and the notice update are one DB transaction.
            # The native queue owns provider delivery; this job never resends it.
            queue = queue_notification(recipients=[settings.pilot_notification_recipient],
                subject=notice.subject, message=notice.message, delayed=True,
                reference_doctype="Home Build Request", reference_name=notice.home_build_request,
                is_notification=True)
            if not queue:
                raise ValueError("No outgoing email queue was created; check the site's Email Account")
            notice.email_queue = queue.name
            notice.delivered_to = settings.pilot_notification_recipient
            notice.status = "Queued"
            notice.last_error = None
            notice.save(ignore_permissions=True)
        except Exception as error:
            frappe.db.rollback(save_point=savepoint)
            frappe.db.set_value("DCR Status Notice", name, "last_error", str(error))
            frappe.log_error(f"{name}: {error}", "DCR Pilot Status Notice")
    # Leave commit ownership to the scheduler, so a failed transaction cannot
    # leave an outbox row without its associated Email Queue.


def refresh_notice_delivery():
    for row in frappe.get_all("DCR Status Notice", filters={"status": "Queued"}, fields=["name", "email_queue"], limit_page_length=100):
        status = frappe.db.get_value("Email Queue", row.email_queue, "status")
        if status in ("Sent", "Error"):
            frappe.db.set_value("DCR Status Notice", row.name, "status", status)
