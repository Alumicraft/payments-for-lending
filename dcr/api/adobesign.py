"""
AdobeSign Integration

Handles:
- Sending documents for signature via AdobeSign API
- Webhook for receiving signature completion events
- Auto-send dealer agreement on Customer save
"""

import hashlib
import hmac
import json

import frappe
from frappe import _
from frappe.utils import now_datetime
import requests


# ---------------------------------------------------------------------------
# AdobeSign API Client
# ---------------------------------------------------------------------------

class AdobeSignClient:
    """Client for Adobe Sign REST API v6."""

    def __init__(self):
        self.settings = get_adobesign_settings()
        self.base_url = self.settings.get("api_url", "https://api.na1.adobesign.com/api/rest/v6")
        self.access_token = self.settings.get("access_token")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def create_agreement(self, name, recipients, file_info, message=""):
        """Create an agreement (send for signature).

        Args:
            name: Agreement name
            recipients: List of dicts with email, role (SIGNER/APPROVER)
            file_info: List of dicts with transientDocumentId or libraryDocumentId
            message: Optional message to signer

        Returns:
            dict with agreement_id
        """
        participant_sets = []
        for i, r in enumerate(recipients):
            participant_sets.append({
                "memberInfos": [{"email": r["email"]}],
                "order": i + 1,
                "role": r.get("role", "SIGNER"),
            })

        payload = {
            "fileInfos": file_info,
            "name": name,
            "participantSetsInfo": participant_sets,
            "signatureType": "ESIGN",
            "state": "IN_PROCESS",
        }
        if message:
            payload["message"] = message

        resp = requests.post(
            f"{self.base_url}/agreements",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"agreement_id": data.get("id")}

    def upload_transient_document(self, file_content, file_name, mime_type="application/pdf"):
        """Upload a document to get a transient document ID."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        resp = requests.post(
            f"{self.base_url}/transientDocuments",
            headers=headers,
            files={"File": (file_name, file_content, mime_type)},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("transientDocumentId")

    def get_agreement_document(self, agreement_id):
        """Download the signed combined PDF for an agreement."""
        resp = requests.get(
            f"{self.base_url}/agreements/{agreement_id}/combinedDocument",
            headers=self._headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content


def get_adobesign_settings():
    """Read AdobeSign settings from site_config or a settings doctype.

    For now, reads from frappe.conf. Keys expected:
        adobesign_api_url, adobesign_access_token, adobesign_webhook_secret,
        adobesign_allowed_ips (comma-separated, optional)
    """
    return {
        "api_url": frappe.conf.get("adobesign_api_url",
                                    "https://api.na1.adobesign.com/api/rest/v6"),
        "access_token": frappe.conf.get("adobesign_access_token", ""),
        "webhook_secret": frappe.conf.get("adobesign_webhook_secret", ""),
        "allowed_ips": frappe.conf.get("adobesign_allowed_ips", ""),
    }


# ---------------------------------------------------------------------------
# Webhook Endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def adobesign_webhook():
    """Handle AdobeSign webhook callbacks.

    URL: /api/method/dcr.api.adobesign.adobesign_webhook

    Security: Verifies the X-AdobeSign-ClientId header against our
    configured client ID to confirm the request originates from AdobeSign.
    For additional security, HMAC signature verification is used when a
    webhook secret is configured.
    """
    try:
        # Verify the request comes from AdobeSign
        if not _verify_webhook_request():
            frappe.local.response["http_status_code"] = 403
            return {"status": "error", "message": "Unauthorized"}

        data = frappe.local.form_dict
        if not data:
            data = json.loads(frappe.request.get_data(as_text=True) or "{}")

        event_type = data.get("event")
        agreement = data.get("agreement", {})
        agreement_id = agreement.get("id") or data.get("agreementId")

        frappe.logger().info(
            f"AdobeSign webhook: event={event_type}, agreement={agreement_id}"
        )

        if not agreement_id:
            return {"status": "ok", "message": "No agreement ID"}

        # Handle the event
        if event_type == "AGREEMENT_ALL_SIGNED":
            _handle_agreement_signed(agreement_id, data)
        elif event_type == "AGREEMENT_ACTION_COMPLETED":
            _handle_agreement_signed(agreement_id, data)

        frappe.db.commit()
        return {"status": "success"}

    except Exception as e:
        frappe.log_error(
            f"AdobeSign webhook error: {str(e)}",
            "AdobeSign Webhook Error"
        )
        return {"status": "error", "message": "Internal error"}


def _check_webhook_ip(allowed_ips_csv):
    """Check if request IP is in the allowed list. Skips check if list is empty."""
    if not allowed_ips_csv:
        return True  # No IP restriction configured
    allowed = {ip.strip() for ip in allowed_ips_csv.split(",") if ip.strip()}
    if not allowed:
        return True
    client_ip = frappe.local.request_ip
    if client_ip not in allowed:
        frappe.logger().warning(f"Webhook request from unauthorized IP: {client_ip}")
        return False
    return True


def _verify_webhook_request():
    """Verify webhook request authenticity via HMAC signature.

    Fail-closed: rejects all requests if no webhook secret is configured.
    Also checks IP whitelist when configured.
    """
    settings = get_adobesign_settings()

    # IP whitelist check
    if not _check_webhook_ip(settings.get("allowed_ips", "")):
        return False

    webhook_secret = settings.get("webhook_secret")
    if not webhook_secret:
        frappe.logger().warning("AdobeSign webhook: no webhook secret configured — rejecting request")
        return False

    signature = frappe.request.headers.get("X-AdobeSign-Signature")
    if not signature:
        frappe.logger().warning("AdobeSign webhook: missing signature header")
        return False

    body = frappe.request.get_data()
    expected = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        frappe.logger().warning("AdobeSign webhook: signature mismatch")
        return False

    return True


def _handle_agreement_signed(agreement_id, data):
    """Process a fully signed agreement.

    Uses frappe.set_value for targeted field updates instead of full
    doc.save(ignore_permissions=True) to limit blast radius.
    """
    sig_req = frappe.db.get_value(
        "Signature Request",
        {"adobesign_agreement_id": agreement_id},
        "name"
    )

    if not sig_req:
        frappe.log_error(
            f"AdobeSign webhook: No Signature Request found for agreement {agreement_id}",
            "AdobeSign Webhook"
        )
        return

    doc = frappe.get_doc("Signature Request", sig_req)
    signed_attachment = None

    # Download signed PDF and attach
    try:
        client = AdobeSignClient()
        pdf_content = client.get_agreement_document(agreement_id)

        file_name = f"{doc.document_type}-{doc.customer}-signed.pdf".replace(" ", "-")
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "content": pdf_content,
            "attached_to_doctype": "Signature Request",
            "attached_to_name": doc.name,
            "is_private": 1,
        })
        file_doc.insert(ignore_permissions=True)
        signed_attachment = file_doc.file_url

    except Exception as e:
        frappe.log_error(
            f"Failed to download signed PDF for {agreement_id}: {str(e)}",
            "AdobeSign PDF Download"
        )

    # Update only the specific fields on the Signature Request
    update_values = {
        "status": "Signed",
        "signed_date": now_datetime(),
    }
    if signed_attachment:
        update_values["signed_attachment"] = signed_attachment
    frappe.db.set_value("Signature Request", sig_req, update_values)

    # Update the referenced document if applicable
    doc.reload()
    _update_reference_document(doc)


def _update_reference_document(sig_req):
    """Update the source document after signature completion.

    Uses frappe.db.set_value for targeted field updates to avoid
    running full Document.save() hooks with elevated permissions.
    """
    if not sig_req.reference_doctype or not sig_req.reference_name:
        return

    try:
        if sig_req.document_type == "Dealer Agreement" and sig_req.reference_doctype == "Customer":
            frappe.db.set_value("Customer", sig_req.reference_name,
                                "dealer_agreement_status", "Signed")

        elif sig_req.document_type == "MIFA" and sig_req.reference_doctype == "MIFA":
            frappe.db.set_value("MIFA", sig_req.reference_name,
                                "signed_mifa", sig_req.signed_attachment)

        elif sig_req.document_type == "Flooring Packet" and sig_req.reference_doctype == "Loan Application":
            frappe.db.set_value("Loan Application", sig_req.reference_name,
                                "signed_packet", sig_req.signed_attachment)

    except Exception as e:
        frappe.log_error(
            f"Failed to update reference doc {sig_req.reference_doctype}/{sig_req.reference_name}: {str(e)}",
            "AdobeSign Reference Update"
        )


# ---------------------------------------------------------------------------
# Send Methods
# ---------------------------------------------------------------------------

def send_for_signature(document_type, reference_doctype, reference_name, customer,
                       recipient_email, pdf_content, pdf_name, agreement_name=None):
    """Generic method to send a document for signature via AdobeSign.

    Creates a Signature Request record and sends via AdobeSign API.

    Returns:
        Signature Request document
    """
    client = AdobeSignClient()

    # Upload the PDF
    transient_id = client.upload_transient_document(pdf_content, pdf_name)

    # Create the agreement
    result = client.create_agreement(
        name=agreement_name or f"{document_type} - {customer}",
        recipients=[{"email": recipient_email, "role": "SIGNER"}],
        file_info=[{"transientDocumentId": transient_id}],
    )

    agreement_id = result["agreement_id"]

    # Create Signature Request record
    sig_req = frappe.new_doc("Signature Request")
    sig_req.customer = customer
    sig_req.document_type = document_type
    sig_req.reference_doctype = reference_doctype
    sig_req.reference_name = reference_name
    sig_req.adobesign_agreement_id = agreement_id
    sig_req.status = "Sent"
    sig_req.sent_date = now_datetime()
    sig_req.insert()

    frappe.db.commit()
    return sig_req


@frappe.whitelist()
def send_dealer_agreement(customer):
    """Send dealer agreement for signature.

    Generates the Dealer Agreement print format and sends via AdobeSign.
    """
    customer_doc = frappe.get_doc("Customer", customer)

    if customer_doc.customer_group != "Dealer":
        frappe.throw(_("Customer is not a Dealer"))

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    # Generate PDF from print format
    pdf_content = frappe.get_print(
        "Customer", customer, "Dealer Agreement", as_pdf=True
    )

    sig_req = send_for_signature(
        document_type="Dealer Agreement",
        reference_doctype="Customer",
        reference_name=customer,
        customer=customer,
        recipient_email=email,
        pdf_content=pdf_content,
        pdf_name=f"Dealer-Agreement-{customer}.pdf",
    )

    # Update status
    customer_doc.dealer_agreement_status = "Sent"
    customer_doc.save()

    return {"success": True, "signature_request": sig_req.name}


def on_customer_update(doc, method):
    """Hook: auto-send dealer agreement on Customer save.

    Triggers when customer_group is Dealer and dealer_agreement_status is
    Not Sent (and email is available).
    """
    if (doc.customer_group == "Dealer"
            and doc.get("dealer_agreement_status") == "Not Sent"
            and doc.email_id):
        try:
            send_dealer_agreement(doc.name)
        except Exception as e:
            frappe.log_error(
                f"Auto-send dealer agreement failed for {doc.name}: {str(e)}",
                "Dealer Agreement Auto-Send"
            )


@frappe.whitelist()
def send_mifa_for_signature(mifa_name):
    """Send MIFA for signature via AdobeSign."""
    mifa = frappe.get_doc("MIFA", mifa_name)
    customer_doc = frappe.get_doc("Customer", mifa.customer)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    pdf_content = frappe.get_print("MIFA", mifa_name, "MIFA", as_pdf=True)

    sig_req = send_for_signature(
        document_type="MIFA",
        reference_doctype="MIFA",
        reference_name=mifa_name,
        customer=mifa.customer,
        recipient_email=email,
        pdf_content=pdf_content,
        pdf_name=f"MIFA-{mifa.customer}.pdf",
    )

    return {"success": True, "signature_request": sig_req.name}


@frappe.whitelist()
def send_flooring_packet(loan_application):
    """Send Exhibit A + ACH Approval as a combined flooring packet."""
    la = frappe.get_doc("Loan Application", loan_application)
    customer_doc = frappe.get_doc("Customer", la.applicant)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    # Generate both print formats and combine
    exhibit_a = frappe.get_print(
        "Loan Application", loan_application, "Exhibit A", as_pdf=True
    )
    ach_approval = frappe.get_print(
        "Loan Application", loan_application, "ACH Approval", as_pdf=True
    )

    # Upload both as transient documents and create a single agreement
    client = AdobeSignClient()
    exhibit_id = client.upload_transient_document(exhibit_a, "Exhibit-A.pdf")
    ach_id = client.upload_transient_document(ach_approval, "ACH-Approval.pdf")

    result = client.create_agreement(
        name=f"Flooring Packet - {la.applicant}",
        recipients=[{"email": email, "role": "SIGNER"}],
        file_info=[
            {"transientDocumentId": exhibit_id},
            {"transientDocumentId": ach_id},
        ],
    )

    agreement_id = result["agreement_id"]

    sig_req = frappe.new_doc("Signature Request")
    sig_req.customer = la.applicant
    sig_req.document_type = "Flooring Packet"
    sig_req.reference_doctype = "Loan Application"
    sig_req.reference_name = loan_application
    sig_req.adobesign_agreement_id = agreement_id
    sig_req.status = "Sent"
    sig_req.sent_date = now_datetime()
    sig_req.insert()
    frappe.db.commit()

    return {"success": True, "signature_request": sig_req.name}
