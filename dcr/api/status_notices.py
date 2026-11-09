"""Durable deal-transition notices, delivered only to a configured pilot mailbox."""
import hashlib
from html import escape
import frappe
from frappe.utils import get_datetime, get_url
from dcr.api.notification_queue import queue_notification
from dcr.dcr.doctype.dcr_pilot_settings.dcr_pilot_settings import validate_pilot_recipient

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
    cutoff = settings.get('pilot_notifications_from')
    if not settings.enable_status_notifications or not settings.pilot_notification_recipient or not cutoff:
        return
    validate_pilot_recipient(settings.pilot_notification_recipient)
    transport = "Native"
    if "emails" in frappe.get_installed_apps():
        service = frappe.get_single("Email Service Settings")
        if service.enabled and service.vercel_service_url:
            transport = "Email Service"
    names = frappe.get_all("DCR Status Notice", filters={
        "status": "Recorded", "creation": [">=", cutoff],
    }, pluck="name", limit_page_length=100)
    for name in names:
        savepoint = "dcr_notice"
        frappe.db.savepoint(savepoint)
        try:
            if frappe.db.get_value("DCR Status Notice", name, "status", for_update=True) != "Recorded":
                continue
            notice = frappe.get_doc("DCR Status Notice", name)
            if notice.status != "Recorded":
                continue
            notice.delivery_transport = transport
            notice.email_queue = None
            if transport == "Native":
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
    # Admission has no external side effects. The scheduler commits the notice
    # and any native Email Queue together; service delivery runs separately.


def refresh_notice_delivery():
    for row in frappe.get_all("DCR Status Notice", filters={"status": "Queued", "email_queue": ["is", "set"]}, fields=["name", "email_queue"], limit_page_length=100):
        status = frappe.db.get_value("Email Queue", row.email_queue, "status")
        if status in ("Sent", "Error"):
            frappe.db.set_value("DCR Status Notice", row.name, "status", status)
    settings = frappe.get_single("DCR Pilot Settings")
    if not settings.enable_status_notifications or not settings.pilot_notifications_from or not settings.pilot_notification_recipient:
        return
    validate_pilot_recipient(settings.pilot_notification_recipient)
    # Five provider timeouts fit within the scheduler's normal time budget.
    # Older windows cannot fill this batch and starve current notices.
    names = frappe.get_all("DCR Status Notice", filters={"status": "Queued",
        "delivery_transport": "Email Service", "email_queue": ["is", "not set"],
        "creation": [">=", settings.pilot_notifications_from],
        "delivered_to": settings.pilot_notification_recipient},
        pluck="name", order_by="creation asc", limit_page_length=5)
    for name in names:
        try:
            _deliver_service_notice(name)
        except Exception as error:
            frappe.db.rollback()
            frappe.log_error(f"{name}: {error}", "DCR Notice Delivery")


def _deliver_service_notice(name):
    """Claim one durable notice before sending. Ambiguous outcomes never auto-retry."""
    notice = frappe.db.get_value("DCR Status Notice", name,
        ["status", "email_queue", "delivery_transport", "creation", "delivered_to", "subject", "message"],
        as_dict=True, for_update=True)
    if not notice:
        return
    settings = frappe.get_single("DCR Pilot Settings")
    if notice.status != "Queued" or notice.email_queue or notice.delivery_transport != "Email Service":
        return
    if (not settings.enable_status_notifications or not settings.pilot_notifications_from
            or get_datetime(notice.creation) < get_datetime(settings.pilot_notifications_from)
            or notice.delivered_to != settings.pilot_notification_recipient):
        return
    validate_pilot_recipient(notice.delivered_to)
    try:
        from emails.email_service.vercel_client import get_service_config, send_email
        from emails.email_service.branding import get_company_branding
        get_service_config()
        branding = get_company_branding()
    except Exception as error:
        frappe.db.set_value("DCR Status Notice", name, "last_error", str(error))
        return
    frappe.db.set_value("DCR Status Notice", name, {"status": "Sending", "last_error": None})
    # Commit the claim before the external call. A crash or timeout leaves a
    # reviewable Sending/Outcome Unknown row, never an automatic duplicate send.
    frappe.db.commit()
    try:
        result = send_email(template="notification", to_email=[notice.delivered_to],
            subject=notice.subject, data={"title": notice.subject, "message": notice.message},
            branding=branding, tags=[{"name": "type", "value": "dcr-pilot-notice"}])
        message_id = result.get("message_id")
        if not message_id:
            raise ValueError("Email service returned no message ID; review delivery before retrying")
        outcome = {"status": "Sent", "provider_message_id": message_id, "last_error": None}
    except Exception as error:
        outcome = {"status": "Outcome Unknown", "last_error": str(error)}
    frappe.db.set_value("DCR Status Notice", name, outcome)
    frappe.db.commit()
