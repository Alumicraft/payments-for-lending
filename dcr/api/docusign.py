"""
DocuSign Integration

Handles:
- JWT Grant authentication (server-to-server, no user interaction)
- Creating envelopes and sending for signature
- Webhook for receiving signature completion events
- Auto-send dealer agreement on Customer save
"""

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _
from frappe.utils import now_datetime
import requests

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None


def _normalize_pem_key(key):
    """Re-format a PEM private key that lost its newlines (e.g. from a Password field)."""
    # Strip surrounding quotes that Frappe Password field may add
    key = key.strip().strip('"').strip("'")
    if "\n" in key:
        return key
    # Strip header/footer, whitespace, then re-chunk at 64 chars
    key = key.replace("-----BEGIN RSA PRIVATE KEY-----", "")
    key = key.replace("-----END RSA PRIVATE KEY-----", "")
    key = key.replace(" ", "").replace("\r", "")
    lines = [key[i:i+64] for i in range(0, len(key), 64)]
    return "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END RSA PRIVATE KEY-----\n"


# ---------------------------------------------------------------------------
# DocuSign API Client
# ---------------------------------------------------------------------------

class DocuSignClient:
    """Client for DocuSign eSignature REST API v2.1 using JWT Grant."""

    def __init__(self):
        self.settings = frappe.get_single("DocuSign Settings")
        if not self.settings.enabled:
            frappe.throw(_("DocuSign integration is not enabled"))
        self.base_url = self.settings.get_base_url()
        self.account_id = self.settings.account_id
        self._access_token = None

    def _get_access_token(self):
        """Get access token via JWT Grant. Cached for 50 minutes."""
        cache_key = "docusign_access_token"
        cached = frappe.cache.get_value(cache_key)
        if cached:
            return cached

        if pyjwt is None:
            frappe.throw(_("PyJWT is required for DocuSign integration. Install with: pip install PyJWT"))

        auth_server = self.settings.get_auth_server()
        integration_key = self.settings.integration_key
        user_id = self.settings.user_id
        private_key = self.settings.get_password("rsa_private_key")
        private_key = _normalize_pem_key(private_key)

        now = int(time.time())
        payload = {
            "iss": integration_key,
            "sub": user_id,
            "aud": auth_server,
            "iat": now,
            "exp": now + 3600,
            "scope": "signature impersonation",
        }

        assertion = pyjwt.encode(payload, private_key, algorithm="RS256")

        resp = requests.post(
            f"https://{auth_server}/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]

        # Cache for 50 minutes (token lasts 60)
        frappe.cache.set_value(cache_key, token, expires_in_sec=3000)
        return token

    def _headers(self):
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def create_envelope(self, name, recipients, documents, webhook_url=None, message=""):
        """Create an envelope (send for signature).

        Args:
            name: Envelope/email subject
            recipients: List of dicts with email, name, role (signer/cc)
            documents: List of dicts with content (bytes), name, file_extension
            webhook_url: URL for per-envelope webhook notification
            message: Optional message to signer

        Returns:
            dict with envelope_id
        """
        signers = []
        for i, r in enumerate(recipients):
            signers.append({
                "email": r["email"],
                "name": r.get("name", r["email"]),
                "recipientId": str(i + 1),
                "routingOrder": str(i + 1),
            })

        doc_list = []
        for i, doc in enumerate(documents):
            doc_list.append({
                "documentBase64": base64.b64encode(doc["content"]).decode(),
                "name": doc["name"],
                "fileExtension": doc.get("file_extension", "pdf"),
                "documentId": str(i + 1),
            })

        payload = {
            "emailSubject": name,
            "documents": doc_list,
            "recipients": {"signers": signers},
            "status": "sent",
        }

        if message:
            payload["emailBlurb"] = message

        # Per-envelope webhook
        if webhook_url:
            payload["eventNotification"] = {
                "url": webhook_url,
                "requireAcknowledgment": "true",
                "loggingEnabled": "true",
                "envelopeEvents": [
                    {"envelopeEventStatusCode": "completed"},
                    {"envelopeEventStatusCode": "declined"},
                    {"envelopeEventStatusCode": "voided"},
                ],
            }

        resp = requests.post(
            f"{self.base_url}/v2.1/accounts/{self.account_id}/envelopes",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"envelope_id": data.get("envelopeId")}

    def get_envelope_document(self, envelope_id):
        """Download the signed combined PDF for an envelope."""
        resp = requests.get(
            f"{self.base_url}/v2.1/accounts/{self.account_id}/envelopes/{envelope_id}/documents/combined",
            headers=self._headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Settings Helper
# ---------------------------------------------------------------------------

def get_docusign_settings():
    """Read DocuSign settings."""
    settings = frappe.get_single("DocuSign Settings")
    return {
        "enabled": settings.enabled,
        "webhook_hmac_key": settings.get_password("webhook_hmac_key") if settings.webhook_hmac_key else "",
        "allowed_ips": settings.allowed_ips or "",
    }


def get_webhook_url():
    """Build the full webhook URL for this site."""
    site_url = frappe.utils.get_url()
    return f"{site_url}/api/method/dcr.api.docusign.docusign_webhook"


# ---------------------------------------------------------------------------
# Webhook Endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def docusign_webhook():
    """Handle DocuSign webhook callbacks.

    URL: /api/method/dcr.api.docusign.docusign_webhook

    Security: Verifies HMAC signature from DocuSign Connect.
    Fail-closed: rejects all requests if no HMAC key is configured.
    """
    try:
        if not _verify_webhook_request():
            frappe.local.response["http_status_code"] = 403
            return {"status": "error", "message": "Unauthorized"}

        data = frappe.request.get_data(as_text=True)
        if not data:
            return {"status": "ok", "message": "Empty payload"}

        payload = json.loads(data)
        envelope_id = payload.get("envelopeId")
        status = payload.get("status", "").lower()

        frappe.logger().info(
            f"DocuSign webhook: status={status}, envelope={envelope_id}"
        )

        if not envelope_id:
            return {"status": "ok", "message": "No envelope ID"}

        if status == "completed":
            _handle_envelope_completed(envelope_id, payload)
        elif status == "declined":
            _handle_envelope_declined(envelope_id, payload)

        frappe.db.commit()
        return {"status": "success"}

    except Exception as e:
        frappe.log_error(
            f"DocuSign webhook error: {str(e)}",
            "DocuSign Webhook Error"
        )
        return {"status": "error", "message": "Internal error"}


def _check_webhook_ip(allowed_ips_csv):
    """Check if request IP is in the allowed list. Skips check if list is empty."""
    if not allowed_ips_csv:
        return True
    allowed = {ip.strip() for ip in allowed_ips_csv.split(",") if ip.strip()}
    if not allowed:
        return True
    client_ip = frappe.local.request_ip
    if client_ip not in allowed:
        frappe.logger().warning(f"DocuSign webhook: request from unauthorized IP: {client_ip}")
        return False
    return True


def _verify_webhook_request():
    """Verify webhook request authenticity via HMAC signature.

    Fail-closed: rejects all requests if no HMAC key is configured.
    Also checks IP whitelist when configured.
    """
    settings = get_docusign_settings()

    if not _check_webhook_ip(settings.get("allowed_ips", "")):
        return False

    hmac_key = settings.get("webhook_hmac_key")
    if not hmac_key:
        frappe.logger().warning("DocuSign webhook: no HMAC key configured — rejecting request")
        return False

    # DocuSign sends HMAC in X-DocuSign-Signature-1 header (base64-encoded)
    signature = frappe.request.headers.get("X-DocuSign-Signature-1")
    if not signature:
        frappe.logger().warning("DocuSign webhook: missing signature header")
        return False

    body = frappe.request.get_data()
    expected = base64.b64encode(
        hmac.new(
            hmac_key.encode(),
            body,
            hashlib.sha256
        ).digest()
    ).decode()

    if not hmac.compare_digest(signature, expected):
        frappe.logger().warning("DocuSign webhook: signature mismatch")
        return False

    return True


def _handle_envelope_completed(envelope_id, data):
    """Process a fully signed envelope."""
    sig_req = frappe.db.get_value(
        "Signature Request",
        {"envelope_id": envelope_id},
        "name"
    )

    if not sig_req:
        frappe.log_error(
            f"DocuSign webhook: No Signature Request found for envelope {envelope_id}",
            "DocuSign Webhook"
        )
        return

    doc = frappe.get_doc("Signature Request", sig_req)
    signed_attachment = None

    # Download signed PDF and attach
    try:
        client = DocuSignClient()
        pdf_content = client.get_envelope_document(envelope_id)

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
            f"Failed to download signed PDF for {envelope_id}: {str(e)}",
            "DocuSign PDF Download"
        )

    update_values = {
        "status": "Signed",
        "signed_date": now_datetime(),
    }
    if signed_attachment:
        update_values["signed_attachment"] = signed_attachment
    frappe.db.set_value("Signature Request", sig_req, update_values)

    doc.reload()
    _update_reference_document(doc)


def _handle_envelope_declined(envelope_id, data):
    """Process a declined envelope."""
    sig_req = frappe.db.get_value(
        "Signature Request",
        {"envelope_id": envelope_id},
        "name"
    )
    if sig_req:
        frappe.db.set_value("Signature Request", sig_req, "status", "Declined")


def _update_reference_document(sig_req):
    """Update the source document after signature completion and send notification."""
    if not sig_req.reference_doctype or not sig_req.reference_name:
        return

    try:
        if sig_req.document_type == "Dealer Agreement" and sig_req.reference_doctype == "Customer":
            frappe.db.set_value("Customer", sig_req.reference_name,
                                "dealer_agreement_status", "Signed")
            _send_signed_email(sig_req)

        elif sig_req.document_type == "MIFA" and sig_req.reference_doctype == "MIFA":
            frappe.db.set_value("MIFA", sig_req.reference_name,
                                "signed_mifa", sig_req.signed_attachment)

        elif sig_req.document_type == "Flooring Packet" and sig_req.reference_doctype == "Loan Application":
            frappe.db.set_value("Loan Application", sig_req.reference_name,
                                "signed_packet", sig_req.signed_attachment)
            _send_signed_email(sig_req)

    except Exception as e:
        frappe.log_error(
            f"Failed to update reference doc {sig_req.reference_doctype}/{sig_req.reference_name}: {str(e)}",
            "DocuSign Reference Update"
        )


def _send_signed_email(sig_req):
    """Send confirmation email after document is signed. Fails silently."""
    try:
        from dcr.api.dcr_email import (
            send_dealer_agreement_signed,
            send_flooring_packet_signed,
        )

        customer_doc = frappe.get_doc("Customer", sig_req.customer)
        email = customer_doc.email_id
        if not email:
            return

        # Prepare signed PDF attachment if available
        attachments = None
        if sig_req.signed_attachment:
            try:
                file_doc = frappe.get_doc("File", {"file_url": sig_req.signed_attachment})
                attachments = [{
                    "filename": file_doc.file_name,
                    "content": base64.b64encode(file_doc.get_content()).decode("utf-8"),
                }]
            except Exception:
                pass  # Send email without attachment

        signed_date = frappe.utils.formatdate(sig_req.signed_date)

        if sig_req.document_type == "Dealer Agreement":
            send_dealer_agreement_signed(
                customer_name=customer_doc.customer_name,
                signed_date=signed_date,
                to_email=email,
                attachments=attachments,
                reference_name=sig_req.reference_name,
            )

        elif sig_req.document_type == "Flooring Packet":
            send_flooring_packet_signed(
                customer_name=customer_doc.customer_name,
                loan_application=sig_req.reference_name,
                signed_date=signed_date,
                to_email=email,
                attachments=attachments,
                reference_name=sig_req.reference_name,
            )

    except Exception as e:
        frappe.log_error(
            f"Failed to send signed email for {sig_req.name}: {str(e)}",
            "DocuSign Signed Email"
        )


# ---------------------------------------------------------------------------
# Send Methods
# ---------------------------------------------------------------------------

def send_for_signature(document_type, reference_doctype, reference_name, customer,
                       recipient_email, recipient_name, pdf_content, pdf_name, envelope_subject=None):
    """Generic method to send a document for signature via DocuSign.

    Creates a Signature Request record and sends via DocuSign API.

    Returns:
        Signature Request document
    """
    client = DocuSignClient()
    webhook_url = get_webhook_url()

    result = client.create_envelope(
        name=envelope_subject or f"{document_type} - {customer}",
        recipients=[{"email": recipient_email, "name": recipient_name, "role": "signer"}],
        documents=[{"content": pdf_content, "name": pdf_name, "file_extension": "pdf"}],
        webhook_url=webhook_url,
    )

    envelope_id = result["envelope_id"]

    sig_req = frappe.new_doc("Signature Request")
    sig_req.customer = customer
    sig_req.document_type = document_type
    sig_req.reference_doctype = reference_doctype
    sig_req.reference_name = reference_name
    sig_req.envelope_id = envelope_id
    sig_req.status = "Sent"
    sig_req.sent_date = now_datetime()
    sig_req.insert()

    frappe.db.commit()
    return sig_req


@frappe.whitelist()
def send_dealer_agreement(customer):
    """Send dealer agreement for signature."""
    customer_doc = frappe.get_doc("Customer", customer)

    if customer_doc.customer_group != "Dealer":
        frappe.throw(_("Customer is not a Dealer"))

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    pdf_content = frappe.get_print(
        "Customer", customer, "Dealer Agreement", as_pdf=True
    )

    sig_req = send_for_signature(
        document_type="Dealer Agreement",
        reference_doctype="Customer",
        reference_name=customer,
        customer=customer,
        recipient_email=email,
        recipient_name=customer_doc.customer_name,
        pdf_content=pdf_content,
        pdf_name=f"Dealer-Agreement-{customer}.pdf",
    )

    customer_doc.dealer_agreement_status = "Sent"
    customer_doc.save()

    return {"success": True, "signature_request": sig_req.name}


@frappe.whitelist()
def send_mifa_for_signature(mifa_name):
    """Send MIFA for signature via DocuSign."""
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
        recipient_name=customer_doc.customer_name,
        pdf_content=pdf_content,
        pdf_name=f"MIFA-{mifa.customer}.pdf",
    )

    return {"success": True, "signature_request": sig_req.name}


@frappe.whitelist()
def send_flooring_packet(loan_application):
    """Send Info Sheet + Exhibit A + ACH Approval as a combined flooring packet."""
    la = frappe.get_doc("Loan Application", loan_application)
    customer_doc = frappe.get_doc("Customer", la.applicant)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    if not la.get("home_build_request"):
        frappe.throw(_("Loan Application must be linked to a Home Build Request"))

    # Render all 3 documents
    info_sheet = frappe.get_print(
        "Home Build Request", la.home_build_request, "New Home Info Sheet", as_pdf=True
    )
    exhibit_a = frappe.get_print(
        "Loan Application", loan_application, "Exhibit A Receipt", as_pdf=True
    )
    ach_approval = frappe.get_print(
        "Loan Application", loan_application, "ACH Recurring Payment Authorization", as_pdf=True
    )

    client = DocuSignClient()
    webhook_url = get_webhook_url()

    result = client.create_envelope(
        name=f"Flooring Packet - {la.applicant}",
        recipients=[{"email": email, "name": customer_doc.customer_name, "role": "signer"}],
        documents=[
            {"content": info_sheet, "name": "New-Home-Info-Sheet.pdf", "file_extension": "pdf"},
            {"content": exhibit_a, "name": "Exhibit-A.pdf", "file_extension": "pdf"},
            {"content": ach_approval, "name": "ACH-Approval.pdf", "file_extension": "pdf"},
        ],
        webhook_url=webhook_url,
    )

    envelope_id = result["envelope_id"]

    sig_req = frappe.new_doc("Signature Request")
    sig_req.customer = la.applicant
    sig_req.document_type = "Flooring Packet"
    sig_req.reference_doctype = "Loan Application"
    sig_req.reference_name = loan_application
    sig_req.envelope_id = envelope_id
    sig_req.status = "Sent"
    sig_req.sent_date = now_datetime()
    sig_req.insert()
    frappe.db.commit()

    return {"success": True, "signature_request": sig_req.name}


@frappe.whitelist()
def send_pre_approval(loan_application):
    """Send Advance Pre-Approval letter as PDF email attachment (no signature needed)."""
    la = frappe.get_doc("Loan Application", loan_application)
    customer_doc = frappe.get_doc("Customer", la.applicant)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    pdf_content = frappe.get_print(
        "Loan Application", loan_application, "Advance Pre-Approval", as_pdf=True
    )

    frappe.sendmail(
        recipients=[email],
        subject=f"Advance Pre-Approval \u2014 {customer_doc.customer_name}",
        message="Please find attached the Advance Pre-Approval letter for your review.",
        attachments=[{
            "fname": f"Advance-Pre-Approval-{la.applicant}.pdf",
            "fcontent": pdf_content,
        }],
        reference_doctype="Loan Application",
        reference_name=loan_application,
    )

    return {"success": True}


@frappe.whitelist()
def send_payoff_letter(loan, payoff_type="Flooring"):
    """Send a payoff letter (FL or COD) as PDF email attachment.

    Args:
        loan: Loan name
        payoff_type: "Flooring" or "COD"
    """
    loan_doc = frappe.get_doc("Loan", loan)
    customer_doc = frappe.get_doc("Customer", loan_doc.applicant)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    print_format = (
        "Dealer Flooring Loan Payoff" if payoff_type == "Flooring"
        else "Dealer Cash on Delivery Payoff"
    )

    pdf_content = frappe.get_print("Loan", loan, print_format, as_pdf=True)

    frappe.sendmail(
        recipients=[email],
        subject=f"Loan Payoff Letter \u2014 {customer_doc.customer_name}",
        message=f"Please find attached your {payoff_type} payoff letter.",
        attachments=[{
            "fname": f"Payoff-{payoff_type}-{loan_doc.applicant}.pdf",
            "fcontent": pdf_content,
        }],
        reference_doctype="Loan",
        reference_name=loan,
    )

    return {"success": True}
