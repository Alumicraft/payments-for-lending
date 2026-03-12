"""
Resend Email Integration for Retailer Application

Sends the retailer application package to factories when a Factory Assignment
is submitted. Uses the emails app for Resend delivery.

Package contents:
1. Retailer Application (from Customer)
2. Dealer's License copy
3. Seller's Permit copy
4. W-9 copy
"""

import frappe
from frappe import _


def send_retailer_application_email(factory_assignment):
    """Send retailer application package to factory.

    Triggered on Factory Assignment submit when retailer_application_status
    is "Submitted".

    Args:
        factory_assignment: Factory Assignment document
    """
    customer = factory_assignment.customer
    factory = factory_assignment.factory

    # Get factory email
    factory_email = frappe.db.get_value("Supplier", factory, "email_id")
    if not factory_email:
        frappe.throw(
            _("Factory {0} does not have an email address. "
              "Please update the Supplier record before submitting.").format(factory)
        )

    # Get customer details
    customer_doc = frappe.get_doc("Customer", customer)
    customer_name = customer_doc.customer_name

    # Collect attachment file URLs
    attachments = []
    attachment_fields = {
        "retailer_application_copy": "Retailer Application",
        "dealer_license_copy": "Dealer's License",
        "sellers_permit_copy": "Seller's Permit",
        "w9_copy": "W-9",
    }

    missing = []
    for field, label in attachment_fields.items():
        file_url = customer_doc.get(field)
        if file_url:
            attachments.append({"file_url": file_url})
        else:
            missing.append(label)

    if missing:
        frappe.throw(
            _("The following documents are missing from the Customer record: {0}. "
              "Please upload them before submitting.").format(", ".join(missing))
        )

    # Get factory name for the email
    factory_name = frappe.db.get_value("Supplier", factory, "supplier_name")

    subject = f"New Dealer Application — {customer_name}"
    message = f"""<p>Dear {factory_name},</p>

<p>Dealer Capital Resources is submitting the following dealer for your review
and approval to order manufactured homes through your factory.</p>

<p><strong>Dealer:</strong> {customer_name}</p>

<p>Please find the following documents attached:</p>
<ol>
    <li>Completed Retailer Application</li>
    <li>Copy of Dealer's License</li>
    <li>Copy of Seller's Permit</li>
    <li>Completed W-9</li>
</ol>

<p>Upon review, please respond with a Letter of Authorization confirming
approval of this dealer.</p>

<p>Thank you,<br>Dealer Capital Resources</p>"""

    frappe.sendmail(
        recipients=[factory_email],
        subject=subject,
        message=message,
        attachments=attachments,
        now=True,
        reference_doctype="Factory Assignment",
        reference_name=factory_assignment.name,
    )

    frappe.msgprint(
        _("Retailer application sent to {0} ({1})").format(factory_name, factory_email),
        indicator="green"
    )
