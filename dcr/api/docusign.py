"""
DocuSign Integration

Handles:
- JWT Grant authentication (server-to-server, no user interaction)
- Creating envelopes and sending for signature
- Webhook for receiving signature completion events
- Staff review of PDFs and recipients before envelope creation
"""

import base64
import hashlib
import hmac
import json
import time
import secrets

import frappe
from dcr.api.access import require_staff
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

    def create_envelope(self, name, recipients, documents, webhook_url=None, message="", client_user_id=None, transaction_id=None):
        """Create an envelope (send for signature).

        Args:
            name: Envelope/email subject
            recipients: List of dicts with email, name, role (signer/cc)
            documents: List of dicts with content (bytes), name, file_extension
            webhook_url: URL for per-envelope webhook notification
            message: Optional message to signer
            client_user_id: If set, uses embedded signing (suppresses DocuSign emails).
                We send the signing link ourselves via our own email system.

        Returns:
            dict with envelope_id
        """
        signers = []
        for i, r in enumerate(recipients):
            signer = {
                "email": r["email"],
                "name": r.get("name", r["email"]),
                "recipientId": str(i + 1),
                "routingOrder": str(i + 1),
                "tabs": {
                    "signHereTabs": [
                        {
                            "anchorString": f"/sig{i + 1}/",
                            "anchorUnits": "pixels",
                            "anchorXOffset": "0",
                            "anchorYOffset": "-10",
                        }
                    ],
                    "dateSignedTabs": [
                        {
                            "anchorString": f"/ds{i + 1}/",
                            "anchorUnits": "pixels",
                            "anchorXOffset": "0",
                            "anchorYOffset": "0",
                        }
                    ],
                },
            }
            if client_user_id:
                signer["clientUserId"] = client_user_id
            signers.append(signer)

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

        if transaction_id:
            payload["transactionId"] = transaction_id

        if message:
            payload["emailBlurb"] = message

        # Per-envelope webhook (JSON format)
        if webhook_url:
            payload["eventNotification"] = {
                "url": webhook_url,
                "deliveryMode": "SIM",
                "requireAcknowledgment": "true",
                "loggingEnabled": "true",
                "includeSoapBody": "false",
                "includeHMAC": "true",
                "eventData": {
                    "version": "restv2.1",
                    "format": "json",
                },
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
        if not resp.ok:
            frappe.log_error(
                f"DocuSign API {resp.status_code}: {resp.text}",
                "DocuSign Envelope Error",
            )
            resp.raise_for_status()
        data = resp.json()
        return {"envelope_id": data.get("envelopeId")}

    def get_signing_url(self, envelope_id, email, name, client_user_id, return_url):
        """Generate an embedded signing URL for a recipient.

        The URL is short-lived (5 min default) so generate it on-demand
        right before redirecting the signer.
        """
        resp = requests.post(
            f"{self.base_url}/v2.1/accounts/{self.account_id}/envelopes/{envelope_id}/views/recipient",
            headers=self._headers(),
            json={
                "returnUrl": return_url,
                "authenticationMethod": "email",
                "email": email,
                "userName": name,
                "clientUserId": client_user_id,
            },
            timeout=30,
        )
        if not resp.ok:
            frappe.log_error(
                f"DocuSign signing URL {resp.status_code}: {resp.text}",
                "DocuSign Signing URL Error",
            )
            resp.raise_for_status()
        return resp.json().get("url")

    def get_envelope_document(self, envelope_id):
        """Download the signed combined PDF for an envelope."""
        resp = requests.get(
            f"{self.base_url}/v2.1/accounts/{self.account_id}/envelopes/{envelope_id}/documents/combined",
            headers=self._headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content

    def get_envelope_status(self, envelope_id):
        """Fetch the current DocuSign envelope status."""
        resp = requests.get(
            f"{self.base_url}/v2.1/accounts/{self.account_id}/envelopes/{envelope_id}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return (resp.json().get("status") or "").lower()


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
        event_data = payload.get("data") or {}
        summary = event_data.get("envelopeSummary") or {}
        envelope_id = payload.get("envelopeId") or event_data.get("envelopeId")
        status = str(payload.get("status") or summary.get("status") or "").lower()
        if not status and str(payload.get("event", "")).startswith("envelope-"):
            status = payload["event"][len("envelope-"):]

        frappe.logger().info(
            f"DocuSign webhook: status={status}, envelope={envelope_id}"
        )

        if not envelope_id:
            return {"status": "ok", "message": "No envelope ID"}

        if status == "completed":
            _handle_envelope_completed(envelope_id, payload)
        elif status in ("declined", "voided"):
            _handle_envelope_declined(envelope_id, payload, "Voided" if status == "voided" else "Declined")

        frappe.db.commit()
        return {"status": "success"}

    except Exception as e:
        frappe.log_error(
            f"DocuSign webhook error: {str(e)}",
            "DocuSign Webhook Error"
        )
        frappe.db.rollback()
        frappe.local.response["http_status_code"] = 500
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
        raise ValueError("Signature Request not yet available; retry this callback")

    frappe.db.get_value("Signature Request", sig_req, "name", for_update=True)
    doc = frappe.get_doc("Signature Request", sig_req)
    if doc.status == "Signed" and doc.signed_attachment:
        return  # The signed PDF and downstream effects were already processed.
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
        raise  # Retry delivery; never mark the source signed without its PDF.

    update_values = {
        "status": "Signed",
        "signed_date": now_datetime(),
    }
    if signed_attachment:
        update_values["signed_attachment"] = signed_attachment
    frappe.db.set_value("Signature Request", sig_req, update_values)

    doc.reload()
    _mirror_signed_attachment_to_reference(doc)
    _update_reference_document(doc)


def _handle_envelope_declined(envelope_id, data, status="Declined"):
    """Record a terminal refusal without regressing an already signed envelope."""
    sig_req = frappe.db.get_value(
        "Signature Request",
        {"envelope_id": envelope_id},
        "name"
    )
    if sig_req:
        current = frappe.db.get_value("Signature Request", sig_req, "status", for_update=True)
        if current != "Signed":
            frappe.db.set_value("Signature Request", sig_req, "status", status)


def _update_reference_document(sig_req):
    """Update the source document after signature completion and send notification."""
    if not sig_req.reference_doctype or not sig_req.reference_name:
        return

    try:
        if sig_req.document_type == "Dealer Agreement" and sig_req.reference_doctype == "Customer":
            frappe.db.set_value("Customer", sig_req.reference_name,
                                "dealer_agreement_status", "Signed")
            _send_signed_email(sig_req)

            # Send welcome email after dealer agreement signed
            try:
                customer_doc = frappe.get_doc("Customer", sig_req.reference_name)
                if customer_doc.email_id:
                    from dcr.api.dcr_email import send_dealer_welcome
                    send_dealer_welcome(
                        customer_name=customer_doc.customer_name,
                        account_id=customer_doc.name,
                        to_email=customer_doc.email_id,
                        reference_name=sig_req.reference_name,
                    )
            except Exception as e:
                frappe.log_error(
                    f"Failed to send welcome email for {sig_req.reference_name}: {str(e)}",
                    "Dealer Welcome Email"
                )

        elif sig_req.document_type == "MIFA" and sig_req.reference_doctype == "MIFA":
            frappe.db.set_value("MIFA", sig_req.reference_name,
                                "signed_mifa", sig_req.signed_attachment)
            _send_signed_email(sig_req)

        elif sig_req.document_type == "Flooring Packet" and sig_req.reference_doctype == "Loan Application":
            if sig_req.get("financial_basis_hash"):
                from dcr.api.financing_basis import financial_snapshot, snapshot_hash
                application = frappe.get_doc("Loan Application", sig_req.reference_name)
                if snapshot_hash(financial_snapshot(application, check_permission=False)) != sig_req.financial_basis_hash:
                    frappe.log_error("Signed packet retained in signature history; its financial terms have changed.",
                                     "Stale Flooring Packet")
                    return
            frappe.db.set_value("Loan Application", sig_req.reference_name,
                                "signed_packet", sig_req.signed_attachment)
            _send_signed_email(sig_req)

    except Exception as e:
        frappe.log_error(
            f"Failed to update reference doc {sig_req.reference_doctype}/{sig_req.reference_name}: {str(e)}",
            "DocuSign Reference Update"
        )


def _mirror_signed_attachment_to_reference(sig_req):
    """Show signed PDFs in the referenced source document's file list too."""
    if not (
        sig_req.reference_doctype
        and sig_req.reference_name
        and sig_req.signed_attachment
    ):
        return

    if frappe.db.exists(
        "File",
        {
            "file_url": sig_req.signed_attachment,
            "attached_to_doctype": sig_req.reference_doctype,
            "attached_to_name": sig_req.reference_name,
        },
    ):
        return

    try:
        signed_file = frappe.get_doc("File", {"file_url": sig_req.signed_attachment})
        mirrored_file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": signed_file.file_name,
                "file_url": sig_req.signed_attachment,
                "attached_to_doctype": sig_req.reference_doctype,
                "attached_to_name": sig_req.reference_name,
                "is_private": signed_file.is_private,
            }
        )
        mirrored_file.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(
            f"Failed to mirror signed PDF to {sig_req.reference_doctype}/{sig_req.reference_name}: {str(e)}",
            "DocuSign Reference Attachment",
        )


def _send_signed_email(sig_req):
    """Send confirmation email after document is signed. Fails silently."""
    try:
        from dcr.api.dcr_email import (
            send_dealer_agreement_signed,
            send_flooring_packet_signed,
            send_mifa_signed,
        )

        customer_doc = frappe.get_doc("Customer", sig_req.customer)
        email = sig_req.get("recipient_email") or customer_doc.email_id
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

        elif sig_req.document_type == "MIFA":
            send_mifa_signed(
                customer_name=customer_doc.customer_name,
                mifa_name=sig_req.reference_name,
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
# Embedded Signing — email with signing link
# ---------------------------------------------------------------------------

def _generate_signing_token(sig_req_name):
    """Generate HMAC token for a signing redirect URL."""
    secret = frappe.local.conf.get("encryption_key") or frappe.local.conf.get("secret_key")
    return hmac.new(
        secret.encode(), sig_req_name.encode(), hashlib.sha256
    ).hexdigest()[:20]


def _verify_signing_token(sig_req_name, token):
    """Verify HMAC token for a signing redirect URL."""
    expected = _generate_signing_token(sig_req_name)
    return hmac.compare_digest(token, expected)


def _get_signing_return_url(sig_req_name, token):
    return frappe.utils.get_url(
        f"/api/method/dcr.api.docusign.signing_complete?sig={sig_req_name}&token={token}"
    )


def _send_signing_email(sig_req, recipient_email, recipient_name, client_user_id):
    """Send our own email with a signing link (since DocuSign emails are suppressed)."""
    token = _generate_signing_token(sig_req.name)
    signing_url = frappe.utils.get_url(
        f"/api/method/dcr.api.docusign.sign_document?sig={sig_req.name}&token={token}"
    )

    from dcr.api.dcr_email import (
        send_dealer_agreement_sent,
        send_flooring_packet_sent,
        send_mifa_sent,
    )

    if sig_req.document_type == "Dealer Agreement":
        send_dealer_agreement_sent(
            customer_name=recipient_name,
            email=recipient_email,
            signing_url=signing_url,
            reference_name=sig_req.reference_name,
        )
    elif sig_req.document_type == "Flooring Packet":
        la = frappe.get_doc("Loan Application", sig_req.reference_name)
        loan_amount = ""
        if la.loan_amount:
            loan_amount = f"{la.loan_amount:,.0f}"
        factory_name = ""
        if la.get("home_build_request"):
            factory_name = frappe.db.get_value(
                "Home Build Request", la.home_build_request, "factory"
            ) or ""

        send_flooring_packet_sent(
            customer_name=recipient_name,
            loan_application=sig_req.reference_name,
            loan_amount=loan_amount,
            factory_name=factory_name,
            to_email=recipient_email,
            signing_url=signing_url,
            reference_name=sig_req.reference_name,
        )
    elif sig_req.document_type == "MIFA":
        mifa = frappe.get_doc("MIFA", sig_req.reference_name)
        credit_limit = ""
        if mifa.credit_limit:
            credit_limit = f"${mifa.credit_limit:,.0f}"

        send_mifa_sent(
            customer_name=recipient_name,
            mifa_name=sig_req.reference_name,
            credit_limit=credit_limit,
            to_email=recipient_email,
            signing_url=signing_url,
            reference_name=sig_req.reference_name,
        )


@frappe.whitelist(allow_guest=True)
def sign_document(sig, token):
    """Guest-accessible redirect: generates a fresh DocuSign signing URL and redirects."""
    if not sig or not token or not _verify_signing_token(sig, token):
        frappe.respond_as_web_page(
            _("Invalid Link"),
            _("This signing link is invalid or has expired. Please contact support."),
            http_status_code=403,
        )
        return

    sig_req = frappe.db.get_value(
        "Signature Request", sig,
        ["envelope_id", "customer", "document_type", "status", "recipient_email", "recipient_name"],
        as_dict=True,
    )

    if not sig_req:
        frappe.respond_as_web_page(
            _("Not Found"),
            _("Signature request not found."),
            http_status_code=404,
        )
        return

    if sig_req.status == "Signed":
        frappe.respond_as_web_page(
            _("Already Signed"),
            _("This document has already been signed. No further action is needed."),
        )
        return

    # Recipient identity must match the envelope, even if Customer is later edited.
    customer_doc = frappe.get_doc("Customer", sig_req.customer)
    recipient_email = sig_req.get("recipient_email") or customer_doc.email_id
    recipient_name = sig_req.get("recipient_name") or customer_doc.customer_name
    client_user_id = f"{sig_req.customer}-{sig_req.document_type}"
    return_url = _get_signing_return_url(sig, token)

    try:
        client = DocuSignClient()
        url = client.get_signing_url(
            envelope_id=sig_req.envelope_id,
            email=recipient_email,
            name=recipient_name,
            client_user_id=client_user_id,
            return_url=return_url,
        )
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = url
    except Exception as e:
        frappe.log_error(f"Failed to generate signing URL: {str(e)}", "DocuSign Signing URL")
        frappe.respond_as_web_page(
            _("Something went wrong"),
            _("Unable to open the signing page. Please try again or contact support."),
            http_status_code=500,
        )


@frappe.whitelist(allow_guest=True)
def signing_complete(sig, token, event=None):
    """DocuSign return URL fallback that finalizes completed embedded signing."""
    if not sig or not token or not _verify_signing_token(sig, token):
        frappe.respond_as_web_page(
            _("Invalid Link"),
            _("This signing completion link is invalid. Please contact support."),
            http_status_code=403,
        )
        return

    sig_req = frappe.db.get_value(
        "Signature Request",
        sig,
        ["envelope_id", "status"],
        as_dict=True,
    )
    if not sig_req:
        frappe.respond_as_web_page(
            _("Not Found"),
            _("Signature request not found."),
            http_status_code=404,
        )
        return

    try:
        if sig_req.get("status") != "Signed":
            client = DocuSignClient()
            envelope_id = sig_req.get("envelope_id")
            if client.get_envelope_status(envelope_id) == "completed":
                _handle_envelope_completed(envelope_id, {"status": "completed"})
                frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            f"Failed to finalize DocuSign return for {sig}: {str(e)}",
            "DocuSign Signing Complete",
        )

    complete_event = event or "signing_complete"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = frappe.utils.get_url(
        f"/docusign-complete?event={complete_event}"
    )


# ---------------------------------------------------------------------------
# Send Methods
# ---------------------------------------------------------------------------

def _signature_context(document_type, reference_name, permission="read"):
    doctypes = {"Dealer Agreement": "Customer", "MIFA": "MIFA", "Flooring Packet": "Loan Application"}
    if document_type not in doctypes or not reference_name:
        frappe.throw(_("Unsupported signature document"))
    doctype = doctypes[document_type]
    require_staff(doctype, reference_name, permission)
    reference = frappe.get_doc(doctype, reference_name)
    reference.check_permission("read")
    reference.check_permission("print")
    customer_name = reference_name if doctype == "Customer" else (reference.customer if doctype == "MIFA" else reference.applicant)
    customer = frappe.get_doc("Customer", customer_name)
    customer.check_permission("read")
    if customer.customer_group != "Dealer" or not customer.email_id:
        frappe.throw(_("A Dealer customer with an email address is required"))
    if document_type == "MIFA" and (not reference.loan_product or not reference.credit_limit or reference.credit_limit <= 0):
        frappe.throw(_("MIFA requires a Loan Product and a positive Credit Limit"))
    prints = [(doctype, reference_name, document_type, f"{document_type.replace(' ', '-')}-{reference_name}.pdf")]
    sources = [reference, customer]
    financial_basis = None
    if document_type == "Flooring Packet":
        if not reference.get("home_build_request"):
            frappe.throw(_("Loan Application must be linked to a Home Build Request"))
        hbr = frappe.get_doc("Home Build Request", reference.home_build_request)
        hbr.check_permission("read")
        hbr.check_permission("print")
        if hbr.customer != customer_name:
            frappe.throw(_("The linked deal belongs to a different dealer"))
        sources.append(hbr)
        from dcr.api.financing_basis import financial_snapshot, money
        financial_basis = financial_snapshot(reference)
        if financial_basis['source'] == 'invoice' and not financial_basis['first_payment_date']:
            frappe.throw(_("Set the First Payment Date before reviewing the final invoice packet."))
        if money(reference.loan_amount) != money(financial_basis["principal"]):
            frappe.throw(_("Save the Loan Application with the final invoice amount before reviewing its packet."))
        prints = [
            ("Home Build Request", hbr.name, "New Home Info Sheet", "New-Home-Info-Sheet.pdf"),
            (doctype, reference_name, "Exhibit A Receipt", "Exhibit-A.pdf"),
            (doctype, reference_name, "ACH Recurring Payment Authorization", "ACH-Approval.pdf"),
        ]
    formats = [(fmt, frappe.db.get_value("Print Format", fmt, "modified")) for _, _, fmt, _ in prints]
    version = [(doc.doctype, doc.name, str(doc.modified)) for doc in sources]
    fingerprint = hashlib.sha256(json.dumps([version, formats, customer.email_id, customer.customer_name, financial_basis], default=str).encode()).hexdigest()
    return {"document_type": document_type, "reference_doctype": doctype, "reference_name": reference_name,
        "customer": customer_name, "recipient_email": customer.email_id, "recipient_name": customer.customer_name,
        "fingerprint": fingerprint, "prints": prints, "financial_basis": financial_basis}


@frappe.whitelist()
def preview_signature(document_type, reference_name):
    """Render and cache the exact review PDFs without contacting DocuSign."""
    context = _signature_context(document_type, reference_name)
    documents = []
    for doctype, name, print_format, filename in context.pop("prints"):
        pdf = frappe.get_print(doctype, name, print_format, as_pdf=True)
        documents.append({"name": filename, "content_base64": base64.b64encode(pdf).decode()})
    token = secrets.token_urlsafe(32)
    context["documents"] = documents
    context["user"] = frappe.session.user
    frappe.cache.set_value(f"dcr:signature-review:{token}", context, expires_in_sec=300)
    return {"review_token": token, "recipient_email": context["recipient_email"], "recipient_name": context["recipient_name"],
        "documents": documents, "expires_in_seconds": 300}


def _send_reviewed_signature(document_type, reference_name, review_token):
    context = _signature_context(document_type, reference_name, permission="email")
    require_staff(context["reference_doctype"], reference_name, "write")
    review = frappe.cache.get_value(f"dcr:signature-review:{review_token}") if review_token else None
    if not review or review.get("user") != frappe.session.user or review.get("document_type") != document_type or review.get("reference_name") != reference_name:
        frappe.throw(_("Preview these documents before sending. The review may have expired."))
    frappe.db.get_value(context["reference_doctype"], reference_name, "name", for_update=True)
    context = _signature_context(document_type, reference_name, permission="email")
    if review.get("fingerprint") != context["fingerprint"]:
        frappe.throw(_("The document or recipient changed. Open a fresh preview before sending."))
    duplicate_filters = {"document_type": document_type,
        "reference_doctype": context["reference_doctype"], "reference_name": reference_name,
        "status": ["in", ["Sent", "Signed", "Outcome Unknown"]]}
    if document_type == "Flooring Packet":
        from dcr.api.financing_basis import snapshot_hash
        duplicate_filters["status"] = ["in", ["Sent", "Outcome Unknown"]]
    existing = frappe.db.exists("Signature Request", duplicate_filters)
    if not existing and document_type == "Flooring Packet":
        existing = frappe.db.exists("Signature Request", {
            **duplicate_filters, "status": "Signed",
            "financial_basis_hash": snapshot_hash(context["financial_basis"]),
        })
    if existing:
        frappe.throw(_("A signature request already exists ({0}). Review it before sending another.").format(existing))
    client = DocuSignClient()
    sig_req = frappe.new_doc("Signature Request")
    for field in ("customer", "document_type", "reference_doctype", "reference_name"):
        sig_req.set(field, context[field])
    sig_req.recipient_email = context["recipient_email"]
    sig_req.recipient_name = context["recipient_name"]
    sig_req.review_hash = hashlib.sha256(json.dumps(review["documents"], sort_keys=True).encode()).hexdigest()
    if context.get("financial_basis"):
        from dcr.api.financing_basis import snapshot_hash
        sig_req.financial_basis_hash = snapshot_hash(context["financial_basis"])
        sig_req.financial_basis = json.dumps(context["financial_basis"], sort_keys=True)
    sig_req.status = "Outcome Unknown"
    sig_req.insert()
    # Durable admission is retained if the request times out or the worker crashes.
    frappe.db.commit()
    frappe.cache.delete_value(f"dcr:signature-review:{review_token}")
    client_user_id = f"{context['customer']}-{document_type}"
    result = client.create_envelope(name=f"{document_type} - {context['customer']}",
        recipients=[{"email": context["recipient_email"], "name": context["recipient_name"], "role": "signer"}],
        documents=[{"content": base64.b64decode(doc["content_base64"]), "name": doc["name"], "file_extension": "pdf"} for doc in review["documents"]],
        webhook_url=get_webhook_url(), client_user_id=client_user_id, transaction_id=sig_req.name)
    if not result.get("envelope_id"):
        frappe.throw(_("DocuSign did not return an envelope ID. Reconcile this request before sending again."))
    sig_req.envelope_id = result["envelope_id"]
    sig_req.status = "Sent"
    sig_req.sent_date = now_datetime()
    sig_req.save()
    if document_type == "Dealer Agreement":
        customer = frappe.get_doc("Customer", context["customer"])
        customer.dealer_agreement_status = "Sent"
        customer.save()
    frappe.db.commit()
    _send_signing_email(sig_req, context["recipient_email"], context["recipient_name"], client_user_id)
    return {"success": True, "signature_request": sig_req.name}


@frappe.whitelist()
def send_dealer_agreement(customer, review_token=None):
    return _send_reviewed_signature("Dealer Agreement", customer, review_token)


@frappe.whitelist()
def send_mifa_for_signature(mifa_name, review_token=None):
    return _send_reviewed_signature("MIFA", mifa_name, review_token)


@frappe.whitelist()
def send_flooring_packet(loan_application, review_token=None):
    return _send_reviewed_signature("Flooring Packet", loan_application, review_token)


@frappe.whitelist()
def send_pre_approval(loan_application):
    """Send Advance Pre-Approval letter as PDF email attachment (no signature needed)."""
    require_staff("Loan Application", loan_application, "email")
    from dcr.api.dcr_email import send_pre_approval as _send_pre_approval_email

    la = frappe.get_doc("Loan Application", loan_application)
    customer_doc = frappe.get_doc("Customer", la.applicant)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    pdf_content = frappe.get_print(
        "Loan Application", loan_application, "Advance Pre-Approval", as_pdf=True
    )

    attachments = [{
        "filename": f"Advance-Pre-Approval-{la.applicant}.pdf",
        "content": base64.b64encode(pdf_content).decode("utf-8"),
    }]

    loan_amount = ""
    if la.loan_amount:
        loan_amount = f"{la.loan_amount:,.0f}"

    _send_pre_approval_email(
        customer_name=customer_doc.customer_name,
        loan_application=loan_application,
        loan_amount=loan_amount,
        to_email=email,
        attachments=attachments,
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
    require_staff("Loan", loan, "email")
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

    from dcr.api.dcr_email import send_payoff_letter as _send_payoff_letter_email

    _send_payoff_letter_email(
        customer_name=customer_doc.customer_name,
        loan=loan,
        payoff_type=payoff_type,
        to_email=email,
        attachments=[{
            "filename": f"Payoff-{payoff_type}-{loan_doc.applicant}.pdf",
            "content": base64.b64encode(pdf_content).decode("utf-8"),
        }],
        reference_name=loan,
    )

    return {"success": True}
