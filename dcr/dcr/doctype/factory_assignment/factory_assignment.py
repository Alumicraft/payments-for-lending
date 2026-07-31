import frappe
from frappe import _
from frappe.model.document import Document


class FactoryAssignment(Document):
    def on_submit(self):
        # Dealer imports represent assignments that were already approved in
        # the source system. Submit them without reopening the retailer
        # application workflow or sending duplicate factory emails.
        if self.retailer_application_status == "Approved":
            return

        # Auto-set status to Submitted
        self.db_set("retailer_application_status", "Submitted")
        self.send_retailer_application()

    def send_retailer_application(self):
        """Send retailer application package to factory."""
        import base64
        from dcr.api.dcr_email import send_retailer_application

        factory_email = frappe.db.get_value("Supplier", self.factory, "email_id")
        if not factory_email:
            frappe.throw(
                _("Factory {0} does not have an email address. "
                  "Please update the Supplier record before submitting.").format(self.factory)
            )

        customer_doc = frappe.get_doc("Customer", self.customer)
        customer_name = customer_doc.customer_name
        dealer_license_no = customer_doc.get("dealer_license_no") or ""

        # Collect attachment files
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
                    attachments.append({"file_url": file_url})
            else:
                missing.append(label)

        if missing:
            frappe.throw(
                _("The following documents are missing from the Customer record: {0}. "
                  "Please upload them before submitting.").format(", ".join(missing))
            )

        factory_name = frappe.db.get_value("Supplier", self.factory, "supplier_name")

        send_retailer_application(
            customer_name=customer_name,
            dealer_license_no=dealer_license_no,
            factory_name=factory_name,
            to_email=factory_email,
            attachments=attachments,
            reference_doctype="Factory Assignment",
            reference_name=self.name,
        )

        frappe.msgprint(
            _("Retailer application sent to {0} ({1})").format(factory_name, factory_email),
            indicator="green"
        )
