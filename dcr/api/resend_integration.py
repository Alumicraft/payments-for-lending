"""
Resend Email Integration for Retailer Application

Sends the retailer application package to factories when a Factory Assignment
is submitted. Uses the emails app Vercel service for branded delivery.

Package contents:
1. Retailer Application (from Customer)
2. Dealer's License copy
3. Seller's Permit copy
4. W-9 copy
"""

import base64
import frappe
from frappe import _

from dcr.api.dcr_email import send_retailer_application


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
    dealer_license_no = customer_doc.get("dealer_license_no") or ""

    # Collect attachment file URLs and convert to base64 for Vercel service
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
            try:
                file_doc = frappe.get_doc("File", {"file_url": file_url})
                file_content = file_doc.get_content()
                attachments.append({
                    "filename": file_doc.file_name or f"{label}.pdf",
                    "content": base64.b64encode(file_content).decode("utf-8"),
                })
            except Exception:
                # Fall back to file_url-based attachment for frappe.sendmail compatibility
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

    send_retailer_application(
        customer_name=customer_name,
        dealer_license_no=dealer_license_no,
        factory_name=factory_name,
        to_email=factory_email,
        attachments=attachments,
        reference_doctype="Factory Assignment",
        reference_name=factory_assignment.name,
    )

    frappe.msgprint(
        _("Retailer application sent to {0} ({1})").format(factory_name, factory_email),
        indicator="green"
    )
