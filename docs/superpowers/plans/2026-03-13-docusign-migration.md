# AdobeSign to DocuSign Migration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AdobeSign integration with DocuSign across all e-signature flows (Dealer Agreement, MIFA, Flooring Packet).

**Architecture:** Swap `AdobeSignClient` for `DocuSignClient` using JWT Grant auth (server-to-server, no user interaction). DocuSign envelopes replace AdobeSign agreements. Per-envelope webhook via `eventNotification` replaces the AdobeSign webhook registration. Same Signature Request doctype tracks the lifecycle. Settings move from `site_config.json` to a `DocuSign Settings` singleton doctype for better management via Frappe UI.

**Tech Stack:** DocuSign eSignature REST API v2.1, JWT Grant (RSA keypair), Python `requests` + `PyJWT`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `dcr/api/docusign.py` | DocuSign client, JWT auth, send methods, webhook handler |
| Create | `dcr/dcr/doctype/docusign_settings/docusign_settings.json` | Singleton settings doctype |
| Create | `dcr/dcr/doctype/docusign_settings/docusign_settings.py` | Settings validation + helpers |
| Create | `dcr/dcr/doctype/docusign_settings/__init__.py` | Package init |
| Create | `dcr/tests/test_docusign_webhook.py` | Webhook HMAC verification tests |
| Modify | `dcr/dcr/doctype/signature_request/signature_request.json` | Rename `adobesign_agreement_id` → `envelope_id`, rename section |
| Modify | `dcr/hooks.py` | Update `doc_events` and add `doctype_js` reference |
| Modify | `dcr/public/js/customer.js` | Update API method paths |
| Delete | `dcr/api/adobesign.py` | Replaced by `docusign.py` |
| Delete | `dcr/tests/test_webhook_security.py` | Replaced by `test_docusign_webhook.py` |
| Modify | `dcr/dcr/doctype/mifa/mifa.json` | Update description text |

---

## Chunk 1: DocuSign Settings Doctype + Client

### Task 1: Create DocuSign Settings Doctype

**Files:**
- Create: `dcr/dcr/doctype/docusign_settings/__init__.py`
- Create: `dcr/dcr/doctype/docusign_settings/docusign_settings.json`
- Create: `dcr/dcr/doctype/docusign_settings/docusign_settings.py`

- [ ] **Step 1: Create `__init__.py`**

```python
# dcr/dcr/doctype/docusign_settings/__init__.py
```

Empty file — just needs to exist for the Python package.

- [ ] **Step 2: Create `docusign_settings.json`**

```json
{
 "actions": [],
 "creation": "2026-03-13 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "issingle": 1,
 "field_order": [
  "enabled",
  "environment",
  "column_break_1",
  "account_id",
  "integration_key",
  "credentials_section",
  "user_id",
  "rsa_private_key",
  "webhook_section",
  "webhook_hmac_key",
  "allowed_ips"
 ],
 "fields": [
  {
   "default": "0",
   "fieldname": "enabled",
   "fieldtype": "Check",
   "label": "Enable DocuSign"
  },
  {
   "default": "Sandbox",
   "fieldname": "environment",
   "fieldtype": "Select",
   "label": "Environment",
   "options": "Sandbox\nProduction",
   "reqd": 1
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "account_id",
   "fieldtype": "Data",
   "label": "Account ID",
   "description": "DocuSign Account ID (GUID)"
  },
  {
   "fieldname": "integration_key",
   "fieldtype": "Data",
   "label": "Integration Key",
   "description": "Also called Client ID in DocuSign"
  },
  {
   "fieldname": "credentials_section",
   "fieldtype": "Section Break",
   "label": "JWT Credentials"
  },
  {
   "fieldname": "user_id",
   "fieldtype": "Data",
   "label": "User ID",
   "description": "DocuSign User ID (GUID) for JWT impersonation"
  },
  {
   "fieldname": "rsa_private_key",
   "fieldtype": "Password",
   "label": "RSA Private Key",
   "description": "PEM-encoded RSA private key for JWT Grant"
  },
  {
   "fieldname": "webhook_section",
   "fieldtype": "Section Break",
   "label": "Webhook Security"
  },
  {
   "fieldname": "webhook_hmac_key",
   "fieldtype": "Password",
   "label": "Webhook HMAC Key",
   "description": "HMAC key configured in DocuSign Connect"
  },
  {
   "fieldname": "allowed_ips",
   "fieldtype": "Data",
   "label": "Allowed IPs",
   "description": "Comma-separated IP whitelist (leave empty for no restriction)"
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-03-13 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "DCR",
 "name": "DocuSign Settings",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "read": 1,
   "role": "System Manager",
   "write": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

- [ ] **Step 3: Create `docusign_settings.py`**

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add dcr/dcr/doctype/docusign_settings/
git commit -m "feat: add DocuSign Settings singleton doctype"
```

---

### Task 2: Create DocuSign Client

**Files:**
- Create: `dcr/api/docusign.py`

- [ ] **Step 1: Write the DocuSign client class with JWT auth**

```python
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
    """Update the source document after signature completion."""
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
            "DocuSign Reference Update"
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


def on_customer_update(doc, method):
    """Hook: auto-send dealer agreement on Customer save."""
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
    """Send Exhibit A + ACH Approval as a combined flooring packet."""
    la = frappe.get_doc("Loan Application", loan_application)
    customer_doc = frappe.get_doc("Customer", la.applicant)

    email = customer_doc.email_id
    if not email:
        frappe.throw(_("Customer does not have an email address"))

    exhibit_a = frappe.get_print(
        "Loan Application", loan_application, "Exhibit A", as_pdf=True
    )
    ach_approval = frappe.get_print(
        "Loan Application", loan_application, "ACH Approval", as_pdf=True
    )

    client = DocuSignClient()
    webhook_url = get_webhook_url()

    result = client.create_envelope(
        name=f"Flooring Packet - {la.applicant}",
        recipients=[{"email": email, "name": customer_doc.customer_name, "role": "signer"}],
        documents=[
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
```

- [ ] **Step 2: Commit**

```bash
git add dcr/api/docusign.py
git commit -m "feat: add DocuSign client with JWT auth, webhook handler, and send methods"
```

---

## Chunk 2: Update Signature Request Doctype + Hooks + JS

### Task 3: Update Signature Request Doctype

**Files:**
- Modify: `dcr/dcr/doctype/signature_request/signature_request.json`

- [ ] **Step 1: Rename AdobeSign fields to DocuSign**

In `signature_request.json`, make these changes:
- `adobesign_section` → `docusign_section`, label "DocuSign"
- `adobesign_agreement_id` → `envelope_id`, label "Envelope ID"
- `column_break_adobe` → `column_break_docusign`
- Update `field_order` to match new names

Updated JSON:

```json
{
 "actions": [],
 "autoname": "format:SIG-{####}",
 "creation": "2024-01-01 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "customer",
  "document_type",
  "status",
  "column_break_1",
  "reference_doctype",
  "reference_name",
  "docusign_section",
  "envelope_id",
  "sent_date",
  "column_break_docusign",
  "signed_date",
  "signed_attachment"
 ],
 "fields": [
  {
   "fieldname": "customer",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Customer",
   "options": "Customer",
   "reqd": 1
  },
  {
   "fieldname": "document_type",
   "fieldtype": "Select",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Document Type",
   "options": "Dealer Agreement\nMIFA\nFlooring Packet",
   "reqd": 1
  },
  {
   "default": "Not Sent",
   "fieldname": "status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Status",
   "options": "Not Sent\nSent\nSigned\nDeclined"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "reference_doctype",
   "fieldtype": "Link",
   "label": "Reference DocType",
   "options": "DocType"
  },
  {
   "fieldname": "reference_name",
   "fieldtype": "Dynamic Link",
   "label": "Reference Name",
   "options": "reference_doctype"
  },
  {
   "fieldname": "docusign_section",
   "fieldtype": "Section Break",
   "label": "DocuSign"
  },
  {
   "fieldname": "envelope_id",
   "fieldtype": "Data",
   "label": "Envelope ID",
   "read_only": 1,
   "description": "DocuSign envelope ID — webhook matching key"
  },
  {
   "fieldname": "sent_date",
   "fieldtype": "Datetime",
   "label": "Sent Date",
   "read_only": 1
  },
  {
   "fieldname": "column_break_docusign",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "signed_date",
   "fieldtype": "Datetime",
   "label": "Signed Date",
   "read_only": 1
  },
  {
   "fieldname": "signed_attachment",
   "fieldtype": "Attach",
   "label": "Signed Document",
   "read_only": 1
  }
 ],
 "index_web_pages_for_search": 1,
 "links": [],
 "modified": "2026-03-13 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "DCR",
 "name": "Signature Request",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  },
  {
   "create": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "Accounts Manager",
   "share": 1,
   "write": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

- [ ] **Step 2: Commit**

```bash
git add dcr/dcr/doctype/signature_request/signature_request.json
git commit -m "refactor: rename Signature Request fields from AdobeSign to DocuSign"
```

---

### Task 4: Update hooks.py

**Files:**
- Modify: `dcr/hooks.py`

- [ ] **Step 1: Change doc_events references from adobesign to docusign**

Change:
```python
"Customer": {
    "on_update": "dcr.api.adobesign.on_customer_update"
},
```

To:
```python
"Customer": {
    "on_update": "dcr.api.docusign.on_customer_update"
},
```

- [ ] **Step 2: Commit**

```bash
git add dcr/hooks.py
git commit -m "refactor: update hooks.py to reference docusign module"
```

---

### Task 5: Update customer.js

**Files:**
- Modify: `dcr/public/js/customer.js`

- [ ] **Step 1: Update the API method path in `send_dealer_agreement`**

Change:
```javascript
method: 'dcr.api.adobesign.send_dealer_agreement',
```

To:
```javascript
method: 'dcr.api.docusign.send_dealer_agreement',
```

- [ ] **Step 2: Commit**

```bash
git add dcr/public/js/customer.js
git commit -m "refactor: update customer.js to call docusign API"
```

---

### Task 6: Update MIFA doctype description

**Files:**
- Modify: `dcr/dcr/doctype/mifa/mifa.json`

- [ ] **Step 1: Update `signed_mifa` field description**

Change `"description": "Populated by AdobeSign webhook"` to `"description": "Populated by DocuSign webhook"`.

- [ ] **Step 2: Commit**

```bash
git add dcr/dcr/doctype/mifa/mifa.json
git commit -m "docs: update MIFA field description to reference DocuSign"
```

---

## Chunk 3: Tests + Cleanup

### Task 7: Write DocuSign Webhook Tests

**Files:**
- Create: `dcr/tests/test_docusign_webhook.py`

- [ ] **Step 1: Write webhook HMAC verification tests**

```python
"""Tests for DocuSign webhook signature verification.

Validates that the HMAC verification correctly accepts genuine requests
and rejects tampered ones. DocuSign uses base64-encoded HMAC-SHA256
in the X-DocuSign-Signature-1 header.
"""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import patch, MagicMock


class TestDocuSignWebhookVerification(unittest.TestCase):

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_valid_hmac_signature_passes(self, mock_settings, mock_frappe):
        secret = "test-webhook-secret-123"
        mock_settings.return_value = {"webhook_hmac_key": secret, "allowed_ips": ""}

        body = b'{"envelopeId":"abc123","status":"completed"}'
        expected_sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()

        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": expected_sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_invalid_hmac_signature_fails(self, mock_settings, mock_frappe):
        secret = "test-webhook-secret-123"
        mock_settings.return_value = {"webhook_hmac_key": secret, "allowed_ips": ""}

        body = b'{"envelopeId":"abc123","status":"completed"}'
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": "bad-signature"}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_missing_signature_header_fails(self, mock_settings, mock_frappe):
        mock_settings.return_value = {"webhook_hmac_key": "secret", "allowed_ips": ""}

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.get_data.return_value = b"{}"
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_no_hmac_key_configured_rejects(self, mock_settings, mock_frappe):
        """Fail-closed: reject all requests when no HMAC key is configured."""
        mock_settings.return_value = {"webhook_hmac_key": "", "allowed_ips": ""}

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_tampered_body_fails(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {"webhook_hmac_key": secret, "allowed_ips": ""}

        original_body = b'{"envelopeId":"abc","status":"completed"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), original_body, hashlib.sha256).digest()
        ).decode()

        tampered_body = b'{"envelopeId":"EVIL","status":"completed"}'
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": sig}
        mock_request.get_data.return_value = tampered_body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_ip_whitelist_blocks_unauthorized_ip(self, mock_settings, mock_frappe):
        mock_settings.return_value = {
            "webhook_hmac_key": "secret",
            "allowed_ips": "1.2.3.4,5.6.7.8",
        }
        mock_frappe.local.request_ip = "9.9.9.9"

        from dcr.api.docusign import _verify_webhook_request
        self.assertFalse(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_ip_whitelist_allows_authorized_ip(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {
            "webhook_hmac_key": secret,
            "allowed_ips": "1.2.3.4,5.6.7.8",
        }
        mock_frappe.local.request_ip = "1.2.3.4"

        body = b'{"envelopeId":"test"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())

    @patch("dcr.api.docusign.frappe")
    @patch("dcr.api.docusign.get_docusign_settings")
    def test_empty_ip_whitelist_skips_check(self, mock_settings, mock_frappe):
        secret = "test-secret"
        mock_settings.return_value = {
            "webhook_hmac_key": secret,
            "allowed_ips": "",
        }

        body = b'{"envelopeId":"test"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        mock_request = MagicMock()
        mock_request.headers = {"X-DocuSign-Signature-1": sig}
        mock_request.get_data.return_value = body
        mock_frappe.request = mock_request

        from dcr.api.docusign import _verify_webhook_request
        self.assertTrue(_verify_webhook_request())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/tristanfleming/Documents/Code/Payments\ For\ Lending
python -m pytest dcr/tests/test_docusign_webhook.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add dcr/tests/test_docusign_webhook.py
git commit -m "test: add DocuSign webhook HMAC verification tests"
```

---

### Task 8: Delete AdobeSign Files

**Files:**
- Delete: `dcr/api/adobesign.py`
- Delete: `dcr/tests/test_webhook_security.py`

- [ ] **Step 1: Remove old AdobeSign files**

```bash
git rm dcr/api/adobesign.py
git rm dcr/tests/test_webhook_security.py
```

- [ ] **Step 2: Verify no remaining AdobeSign references**

```bash
grep -ri "adobesign\|adobe.sign\|adobe_sign" dcr/ --include="*.py" --include="*.js" --include="*.json"
```

Expected: No output (no remaining references). PLAN.md references are fine — it's documentation.

- [ ] **Step 3: Commit**

```bash
git rm dcr/api/adobesign.py dcr/tests/test_webhook_security.py
git commit -m "refactor: remove AdobeSign integration files (replaced by DocuSign)"
```

---

### Task 9: Add PyJWT Dependency

**Files:**
- Modify: `setup.py` (or `pyproject.toml` if present)

- [ ] **Step 1: Add PyJWT to install_requires**

In `setup.py`, add `"PyJWT[crypto]"` to the `install_requires` list. The `[crypto]` extra includes `cryptography` for RS256 support.

- [ ] **Step 2: Commit**

```bash
git add setup.py
git commit -m "feat: add PyJWT dependency for DocuSign JWT auth"
```

---

## DocuSign Setup Instructions (Post-Deploy)

After deploying, configure DocuSign:

1. **Create DocuSign Developer Account** at https://go.docusign.com/sandbox/productshot/
2. In DocuSign Admin → **API and Keys**:
   - Note your **Account ID** and **User ID** (both GUIDs)
   - Create an **Integration Key** (Client ID)
   - Generate an **RSA Keypair** — download the private key
   - Add redirect URI (not used for JWT but required): `https://yoursite.frappe.cloud`
3. **Grant consent** (one-time): Visit `https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=YOUR_INTEGRATION_KEY&redirect_uri=https://yoursite.frappe.cloud`
4. In Frappe → **DocuSign Settings**:
   - Enable DocuSign
   - Environment: Sandbox
   - Paste Account ID, Integration Key, User ID
   - Paste RSA Private Key (full PEM including BEGIN/END lines)
5. **Webhook HMAC**: In DocuSign Admin → Connect, create a webhook configuration with your HMAC key. Paste the same key into DocuSign Settings → Webhook HMAC Key.
6. **Webhook URL**: `https://yoursite.frappe.cloud/api/method/dcr.api.docusign.docusign_webhook`
