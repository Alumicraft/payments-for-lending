import frappe
from frappe.model.document import Document


class DocuSignSettings(Document):
    def validate(self):
        if self.enabled:
            for field, label in [
                ("account_id", "Account ID"),
                ("integration_key", "Integration Key"),
                ("user_id", "User ID"),
                ("rsa_private_key", "RSA Private Key"),
            ]:
                if not self.get(field):
                    frappe.throw(f"{label} is required when DocuSign is enabled")

    def get_base_url(self):
        if self.environment == "Production":
            return "https://na1.docusign.net/restapi"
        return "https://demo.docusign.net/restapi"

    def get_auth_server(self):
        if self.environment == "Production":
            return "account.docusign.com"
        return "account-d.docusign.com"
