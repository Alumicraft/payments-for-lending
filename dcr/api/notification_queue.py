"""Queue transactional notices through Frappe, bypassing immediate email overrides."""


def queue_notification(**kwargs):
    # The Emails app monkey-patches frappe.sendmail and may send via Vercel
    # immediately. Import the native function so queue creation and the event
    # receipt stay in one database transaction regardless of request hooks.
    from frappe.email import sendmail

    kwargs["delayed"] = True
    kwargs["now"] = False
    return sendmail(**kwargs)
