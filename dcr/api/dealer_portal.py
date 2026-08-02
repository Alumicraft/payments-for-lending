"""Dealer-facing portal APIs.

The Desk application has broad, role-based permissions while the dealer portal
needs a much narrower, row-scoped surface.  Every method in this module derives
the dealer Customer from the logged-in Frappe Portal User and serializes only
the fields the dealer needs.  Browser-provided Customer names are deliberately
not accepted as authorization inputs.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import quote

import frappe
from frappe import _


PORTAL_STATUS_FIELD = "custom_portal_status"
PORTAL_SUBMITTED_ON_FIELD = "custom_portal_submitted_on"
PORTAL_SUBMITTED_BY_FIELD = "custom_portal_submitted_by"

PORTAL_STATUSES = (
    "Draft",
    "Submitted for Review",
    "Changes Requested",
    "Accepted",
)

DEALER_DOCUMENT_FIELDS = {
    "dealer_license_copy": "Dealer license",
    "sellers_permit_copy": "Seller's permit",
    "w9_copy": "W-9",
    "retailer_application_copy": "Retailer application",
}

HBR_INPUT_FIELDS = {
    "home_type",
    "financing_type",
    "property_type",
    "factory",
    "floor_plan",
    "home_serial_no",
    "home_invoice_plus_freight",
    "community_name",
    "delivery_address",
    "address_line_2",
    "city",
    "state",
    "zip",
    "space_number",
    "contact_name",
    "contact_phone",
    "gated",
    "access_code",
    "space_rent",
    "selling_price",
    "customer_deposit",
    "end_buyer_lender",
    "escrow_contact",
    "escrow_phone",
    "escrow_number",
    "broker_contact",
    "broker_phone",
}

HBR_SELECT_OPTIONS = {
    "home_type": {"Spec", "Customer Sold"},
    "financing_type": {"Cash", "Floored"},
    "property_type": {"Park", "Private Property"},
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx"}
ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

LOAN_APPLICATION_FIELDS = (
    "name",
    "status",
    "loan_amount",
    "qualifying_amount",
    "rate_of_interest",
    "total_payable_interest",
    "total_interest_payable",
    "total_payable_amount",
    "total_payment",
    "signed_packet",
    "modified",
)

LOAN_FIELDS = (
    "name",
    "status",
    "qualifying_amount",
    "loan_amount",
    "rate_of_interest",
    "total_interest_payable",
    "total_payable_interest",
    "total_payable_amount",
    "total_payment",
    "modified",
)


def _value(doc, fieldname, default=None):
    """Read a Frappe document, dict, or test double consistently."""
    if doc is None:
        return default
    try:
        result = doc.get(fieldname)
    except AttributeError:
        result = getattr(doc, fieldname, default)
    return default if result is None else result


def _json_value(value):
    """Return a value that Frappe's JSON response can serialize."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return float(value)
    return value


def _deny(message):
    frappe.throw(_(message))


def _session_user():
    user = getattr(getattr(frappe, "session", None), "user", None)
    if not user or user in ("Guest", "guest"):
        _deny("Please sign in to access the dealer portal.")
    return user


def _portal_user_customers(user):
    """Resolve Customer parents from ERPNext's standard Portal User table."""
    rows = frappe.get_all(
        "Portal User",
        filters={"parenttype": "Customer", "user": user},
        fields=["parent"],
        ignore_permissions=True,
        limit_page_length=0,
    )
    names = []
    for row in rows or []:
        parent = _value(row, "parent")
        if parent and parent not in names:
            names.append(parent)
    return names


def get_current_dealer_customer():
    """Return the one active Dealer Customer owned by the current portal user."""
    user = _session_user()
    customers = _portal_user_customers(user)
    if not customers:
        _deny("Your account is not linked to an active DCR dealer.")
    if len(customers) != 1:
        _deny("Your account is linked to more than one dealer. Please contact DCR support.")

    customer = frappe.db.get_value(
        "Customer",
        customers[0],
        ["name", "customer_name", "customer_group", "disabled", "email_id"],
        as_dict=True,
    )
    if not customer:
        _deny("Your dealer account could not be found.")
    if _value(customer, "customer_group") != "Dealer" or _value(customer, "disabled"):
        _deny("Your dealer account is not active.")
    return customer


def _has_field(doctype, fieldname):
    try:
        return bool(frappe.get_meta(doctype).has_field(fieldname))
    except Exception:
        try:
            return bool(frappe.db.has_column(doctype, fieldname))
        except Exception:
            return False


def _available_fields(doctype, fields):
    return [field for field in fields if field == "name" or _has_field(doctype, field)]


def _portal_status(doc):
    status = _value(doc, PORTAL_STATUS_FIELD)
    if status in PORTAL_STATUSES:
        return status
    return "Accepted" if _value(doc, "docstatus") == 1 else "Draft"


def _get_owned_hbr(name, customer=None):
    customer = customer or get_current_dealer_customer()
    if not name or not frappe.db.exists(
        "Home Build Request", {"name": name, "customer": _value(customer, "name")}
    ):
        _deny("That home request is not available in your dealer account.")
    # The ownership query above is the authorization boundary.  The portal
    # intentionally does not grant Desk read permission on HBRs, so load the
    # verified row without running the broad DocType permission check.
    return frappe.get_doc("Home Build Request", name, check_permission=False)


def _require_editable_hbr(hbr):
    if _value(hbr, "docstatus") != 0:
        _deny("This home request is locked after DCR submission.")
    if _portal_status(hbr) not in {"Draft", "Changes Requested"}:
        _deny("This home request is not accepting dealer changes.")


def _require_uploadable_hbr(hbr):
    if _value(hbr, "docstatus") != 0:
        _deny("This home request is locked after DCR submission.")
    if _portal_status(hbr) not in {"Draft", "Changes Requested", "Submitted for Review"}:
        _deny("This home request is not accepting dealer documents.")


def _require_active_factory(customer_name, factory):
    if not factory:
        _deny("Choose an assigned factory before saving the home request.")
    if not frappe.db.exists(
        "Factory Assignment",
        {"customer": customer_name, "factory": factory, "docstatus": 1, "active": 1},
    ):
        _deny("That factory is not assigned to your dealer account.")


def _validate_portal_serial(serial, current_name=None):
    """Reject duplicate serials without leaking another dealer's HBR name."""
    if not serial:
        return
    filters = {"home_serial_no": serial}
    if current_name:
        filters["name"] = ["!=", current_name]
    if frappe.db.exists("Home Build Request", filters):
        _deny("That home serial number is already in use.")


def _hbr_document_items(hbr):
    rows = []
    for row in _value(hbr, "doc_checklist", []) or []:
        document_type = _value(row, "document_type")
        if not document_type:
            continue
        rows.append(
            {
                "document_type": document_type,
                "uploaded": bool(_value(row, "attachment")),
                # A waiver is an internal decision. Expose only whether the
                # checklist item is complete, not why it is complete.
                "complete": bool(_value(row, "attachment") or _value(row, "waived")),
            }
        )
    return rows


def _latest_related(doctype, filters, fields):
    available = _available_fields(doctype, fields)
    if not available:
        return {}
    rows = frappe.get_all(
        doctype,
        filters=filters,
        fields=available,
        order_by="modified desc",
        limit_page_length=1,
        ignore_permissions=True,
    )
    return rows[0] if rows else {}


def _loan_summary(hbr_name):
    application = (
        _latest_related(
            "Loan Application",
            {"home_build_request": hbr_name, "docstatus": ["!=", 2]},
            LOAN_APPLICATION_FIELDS,
        )
        if _has_field("Loan Application", "home_build_request")
        else {}
    )
    loan = (
        _latest_related(
            "Loan",
            {"home_build_request": hbr_name, "docstatus": ["!=", 2]},
            LOAN_FIELDS,
        )
        if _has_field("Loan", "home_build_request")
        else {}
    )
    source = loan or application
    if not source:
        return {"status": "Not Started", "source": None, "signed": False}

    amount = _value(source, "qualifying_amount") or _value(source, "loan_amount")
    total_interest = (
        _value(source, "total_interest_payable")
        or _value(source, "total_payable_interest")
    )
    total_payable = _value(source, "total_payable_amount") or _value(source, "total_payment")
    return {
        "source": "Loan" if loan else "Loan Application",
        "name": _value(source, "name"),
        "status": _value(source, "status") or "Applied",
        "principal": _json_value(amount),
        "interest_rate": _json_value(_value(source, "rate_of_interest")),
        "total_interest": _json_value(total_interest),
        "total_payable": _json_value(total_payable),
        "signed": bool(_value(application, "signed_packet")),
    }


def _serialize_hbr(hbr, customer=None):
    documents = _hbr_document_items(hbr)
    missing = [item["document_type"] for item in documents if not item["complete"]]
    factory = _value(hbr, "factory")
    factory_label = None
    if factory:
        factory_label = frappe.db.get_value("Supplier", factory, "supplier_name") or factory
    portal_status = _portal_status(hbr)
    editable_fields = None
    if portal_status in {"Draft", "Changes Requested"}:
        editable_fields = {
            fieldname: _json_value(_value(hbr, fieldname))
            for fieldname in HBR_INPUT_FIELDS
            if _has_field("Home Build Request", fieldname)
        }

    return {
        "name": _value(hbr, "name"),
        "portal_status": portal_status,
        "docstatus": _value(hbr, "docstatus"),
        "modified": _json_value(_value(hbr, "modified")),
        "home_type": _value(hbr, "home_type"),
        "financing_type": _value(hbr, "financing_type"),
        "property_type": _value(hbr, "property_type"),
        "factory": {"name": factory, "label": factory_label} if factory else None,
        "floor_plan": _value(hbr, "floor_plan"),
        "home_serial_no": _value(hbr, "home_serial_no"),
        "quoted_amount": _json_value(_value(hbr, "home_invoice_plus_freight")),
        "order_stage": _value(hbr, "custom_order_stage") or ("Draft" if _value(hbr, "docstatus") == 0 else "Pending"),
        "loan_stage": _value(hbr, "custom_loan_stage") or "Not Started",
        "editable": editable_fields,
        "documents": {
            "items": documents,
            "required": len(documents),
            "uploaded": sum(1 for item in documents if item["uploaded"]),
            "complete": len(documents) - len(missing),
            "missing": missing,
        },
        "loan": _loan_summary(_value(hbr, "name")),
    }


def _get_onboarding_documents(customer):
    fields = [field for field in DEALER_DOCUMENT_FIELDS if _has_field("Customer", field)]
    values = (
        frappe.db.get_value("Customer", _value(customer, "name"), fields, as_dict=True) or {}
        if fields
        else {}
    )
    return [
        {
            "fieldname": fieldname,
            "label": label,
            "uploaded": bool(_value(values, fieldname)),
        }
        for fieldname, label in DEALER_DOCUMENT_FIELDS.items()
    ]


def _get_factories(customer):
    assignments = frappe.get_all(
        "Factory Assignment",
        filters={
            "customer": _value(customer, "name"),
            "docstatus": 1,
            "active": 1,
        },
        fields=["factory"],
        order_by="factory asc",
        ignore_permissions=True,
        limit_page_length=0,
    )
    factories = []
    for row in assignments or []:
        name = _value(row, "factory")
        if not name:
            continue
        factories.append(
            {
                "name": name,
                "label": frappe.db.get_value("Supplier", name, "supplier_name") or name,
            }
        )
    return factories


def _get_signatures(customer):
    fields = [
        "name",
        "document_type",
        "status",
        "reference_doctype",
        "reference_name",
        "sent_date",
        "signed_date",
    ]
    rows = frappe.get_all(
        "Signature Request",
        filters={"customer": _value(customer, "name")},
        fields=_available_fields("Signature Request", fields),
        order_by="modified desc",
        limit_page_length=50,
        ignore_permissions=True,
    )
    return [
        {
            "name": _value(row, "name"),
            "document_type": _value(row, "document_type"),
            "status": _value(row, "status"),
            "sent_date": _json_value(_value(row, "sent_date")),
            "signed_date": _json_value(_value(row, "signed_date")),
            "actionable": _value(row, "status") == "Sent",
        }
        for row in rows or []
    ]


def _get_ach_accounts(customer):
    if not _has_field("Bank Account", "custom_ach_status"):
        return []
    fields = [
        "bank",
        "custom_ach_status",
        "custom_account_last_four",
        "is_default",
    ]
    rows = frappe.get_all(
        "Bank Account",
        filters={
            "party_type": "Customer",
            "party": _value(customer, "name"),
            "custom_ach_status": ["in", ["Active", "Paused"]],
        },
        fields=_available_fields("Bank Account", fields),
        order_by="is_default desc, modified desc",
        limit_page_length=20,
        ignore_permissions=True,
    )
    result = []
    for row in rows or []:
        bank = _value(row, "bank")
        result.append(
            {
                "bank_name": frappe.db.get_value("Bank", bank, "bank_name") if bank else "",
                "last4": _value(row, "custom_account_last_four"),
                "status": _value(row, "custom_ach_status"),
                "is_default": bool(_value(row, "is_default")),
            }
        )
    return result


def _plaid_is_available():
    try:
        from dcr.api.achq_integration import is_plaid_available

        return bool(is_plaid_available().get("available"))
    except Exception:
        return False


@frappe.whitelist()
def get_portal_context():
    """Return the complete dealer-safe dashboard payload."""
    customer = get_current_dealer_customer()
    hbr_fields = _available_fields(
        "Home Build Request",
        [
            "name",
            "customer",
            "docstatus",
            "modified",
            "home_type",
            "financing_type",
            "property_type",
            "factory",
            "floor_plan",
            "home_serial_no",
            "home_invoice_plus_freight",
            "custom_order_stage",
            "custom_loan_stage",
            PORTAL_STATUS_FIELD,
        ],
    )
    hbrs = frappe.get_all(
        "Home Build Request",
        filters={"customer": _value(customer, "name"), "docstatus": ["<", 2]},
        fields=hbr_fields,
        order_by="modified desc",
        limit_page_length=100,
        ignore_permissions=True,
    )
    deals = []
    for row in hbrs or []:
        # Load the child checklist only after the parent query has proven the
        # Customer relationship.
        hbr = frappe.get_doc(
            "Home Build Request",
            _value(row, "name"),
            check_permission=False,
        )
        deals.append(_serialize_hbr(hbr, customer))

    onboarding = _get_onboarding_documents(customer)
    signatures = _get_signatures(customer)
    return {
        "customer": {
            "name": _value(customer, "name"),
            "label": _value(customer, "customer_name") or _value(customer, "name"),
            "email": _value(customer, "email_id"),
        },
        "factories": _get_factories(customer),
        "deals": deals,
        "onboarding_documents": onboarding,
        "signatures": signatures,
        "ach": {
            "accounts": _get_ach_accounts(customer),
            "available": _plaid_is_available(),
        },
    }


@frappe.whitelist()
def get_deal(name):
    """Return one dealer-owned HBR and its safe related data."""
    customer = get_current_dealer_customer()
    return _serialize_hbr(_get_owned_hbr(name, customer), customer)


def _parse_payload(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            _deny("The home request payload is invalid.")
    if not isinstance(payload, dict):
        _deny("The home request payload is invalid.")
    unknown = set(payload) - HBR_INPUT_FIELDS
    if unknown:
        _deny("The home request contains an unsupported field.")
    for fieldname, options in HBR_SELECT_OPTIONS.items():
        if fieldname in payload and payload[fieldname] not in options:
            _deny(f"The {fieldname.replace('_', ' ')} value is invalid.")
    return payload


@frappe.whitelist()
def save_hbr_draft(payload=None, name=None):
    """Create or update a dealer-owned HBR draft."""
    customer = get_current_dealer_customer()
    payload = _parse_payload(payload or {})
    if name:
        hbr = _get_owned_hbr(name, customer)
        _require_editable_hbr(hbr)
        _require_active_factory(
            _value(customer, "name"), payload.get("factory") or _value(hbr, "factory")
        )
        _validate_portal_serial(payload.get("home_serial_no"), name)
        for fieldname, value in payload.items():
            hbr.set(fieldname, value)
        hbr.save(ignore_permissions=True)
    else:
        _require_active_factory(_value(customer, "name"), payload.get("factory"))
        _validate_portal_serial(payload.get("home_serial_no"))
        hbr = frappe.new_doc("Home Build Request")
        hbr.customer = _value(customer, "name")
        for fieldname, value in payload.items():
            hbr.set(fieldname, value)
        if _has_field("Home Build Request", PORTAL_STATUS_FIELD):
            hbr.set(PORTAL_STATUS_FIELD, "Draft")
        hbr.insert(ignore_permissions=True)

    return _serialize_hbr(hbr, customer)


@frappe.whitelist()
def submit_hbr_for_review(name):
    """Move a dealer-owned draft into DCR's review queue without submitting it."""
    customer = get_current_dealer_customer()
    hbr = _get_owned_hbr(name, customer)
    _require_editable_hbr(hbr)
    current_status = _portal_status(hbr)
    if current_status not in {"Draft", "Changes Requested"}:
        _deny("This home request is already with DCR for review.")

    if not _has_field("Home Build Request", PORTAL_STATUS_FIELD):
        # Never fall back to the native ``status`` field: that would make the
        # review transition ambiguous on a site whose migration is incomplete.
        _deny("The dealer review workflow is not configured yet. Please contact DCR support.")

    updates = {PORTAL_STATUS_FIELD: "Submitted for Review"}
    if _has_field("Home Build Request", PORTAL_SUBMITTED_ON_FIELD):
        updates[PORTAL_SUBMITTED_ON_FIELD] = frappe.utils.now_datetime()
    if _has_field("Home Build Request", PORTAL_SUBMITTED_BY_FIELD):
        updates[PORTAL_SUBMITTED_BY_FIELD] = _session_user()
    frappe.db.set_value("Home Build Request", name, updates, update_modified=True)
    hbr.reload()
    return _serialize_hbr(hbr, customer)


def _request_file():
    request = getattr(getattr(frappe, "local", None), "request", None)
    if request is None:
        request = getattr(frappe, "request", None)
    files = getattr(request, "files", None)
    if files is None or not hasattr(files, "get"):
        return None
    return files.get("file")


def _safe_file_name(file_name):
    basename = os.path.basename(file_name or "document")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", basename).strip(".")
    return cleaned[:180] or "document"


def _validate_upload(file):
    if file is None:
        _deny("Choose a file to upload.")
    file_name = _safe_file_name(getattr(file, "filename", "document"))
    extension = os.path.splitext(file_name)[1].lower()
    content_type = getattr(file, "mimetype", None) or getattr(file, "content_type", None)
    if extension not in ALLOWED_UPLOAD_EXTENSIONS or (
        content_type and content_type not in ALLOWED_UPLOAD_TYPES
    ):
        _deny("Upload a PDF, Word document, or image file.")
    content = file.read()
    if not content:
        _deny("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        _deny("Files must be 10 MB or smaller.")
    return file_name, content


def _insert_private_file(file_name, content, doctype, name, fieldname):
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "content": content,
            "attached_to_doctype": doctype,
            "attached_to_name": name,
            "attached_to_field": fieldname,
            "is_private": 1,
        }
    )
    file_doc.insert(ignore_permissions=True)
    return file_doc


@frappe.whitelist()
def upload_document(target_type, target_name=None, document_type=None):
    """Upload one private onboarding or HBR checklist document."""
    customer = get_current_dealer_customer()
    file_name, content = _validate_upload(_request_file())

    if target_type == "customer":
        if document_type not in DEALER_DOCUMENT_FIELDS:
            _deny("That onboarding document is not supported.")
        if not _has_field("Customer", document_type):
            _deny("That onboarding document is not configured yet.")
        if target_name and target_name != _value(customer, "name"):
            _deny("That dealer account is not available.")
        target_name = _value(customer, "name")
        file_doc = _insert_private_file(
            file_name,
            content,
            "Customer",
            target_name,
            document_type,
        )
        customer_doc = frappe.get_doc("Customer", target_name, check_permission=False)
        customer_doc.set(document_type, file_doc.file_url)
        customer_doc.save(ignore_permissions=True)
    elif target_type == "hbr":
        hbr = _get_owned_hbr(target_name, customer)
        _require_uploadable_hbr(hbr)
        row = next(
            (
                row
                for row in (_value(hbr, "doc_checklist", []) or [])
                if _value(row, "document_type") == document_type
            ),
            None,
        )
        if row is None:
            _deny("That document is not required for this home request.")
        file_doc = _insert_private_file(
            file_name,
            content,
            "Home Build Request",
            target_name,
            "doc_checklist",
        )
        row.attachment = file_doc.file_url
        hbr.save(ignore_permissions=True)
    else:
        _deny("That upload target is not supported.")

    return {
        "target_type": target_type,
        "target_name": target_name,
        "document_type": document_type,
        "file_name": file_name,
        "uploaded": True,
    }


def _document_url(customer, target_type, target_name, document_type):
    if target_type == "customer":
        if target_name and target_name != _value(customer, "name"):
            _deny("That dealer account is not available.")
        fieldname = document_type
        if fieldname not in DEALER_DOCUMENT_FIELDS:
            _deny("That onboarding document is not supported.")
        if not _has_field("Customer", fieldname):
            _deny("That onboarding document is not configured yet.")
        value = frappe.db.get_value("Customer", _value(customer, "name"), fieldname)
        return "Customer", _value(customer, "name"), fieldname, value
    if target_type == "hbr":
        hbr = _get_owned_hbr(target_name, customer)
        row = next(
            (
                row
                for row in (_value(hbr, "doc_checklist", []) or [])
                if _value(row, "document_type") == document_type
            ),
            None,
        )
        if row is None:
            _deny("That document is not required for this home request.")
        return "Home Build Request", target_name, "doc_checklist", _value(row, "attachment")
    _deny("That download target is not supported.")


@frappe.whitelist()
def download_document(target_type, target_name=None, document_type=None):
    """Stream an owned private file after checking its parent relationship."""
    customer = get_current_dealer_customer()
    doctype, name, fieldname, file_url = _document_url(
        customer, target_type, target_name, document_type
    )
    if not file_url:
        _deny("That document has not been uploaded yet.")
    file_doc = frappe.get_doc("File", {"file_url": file_url}, check_permission=False)
    if (
        _value(file_doc, "attached_to_doctype") != doctype
        or _value(file_doc, "attached_to_name") != name
        or _value(file_doc, "attached_to_field") != fieldname
        or not _value(file_doc, "is_private")
    ):
        _deny("That document is not attached to the requested record.")

    response = frappe.local.response
    response["type"] = "download"
    response["filename"] = file_doc.file_name
    response["filecontent"] = file_doc.get_content()
    response["content-type"] = getattr(file_doc, "content_type", None) or "application/octet-stream"


@frappe.whitelist()
def get_ach_setup_url():
    """Return a short-lived Plaid setup URL for the current dealer."""
    customer = get_current_dealer_customer()
    from dcr.api.achq_integration import is_plaid_available
    from dcr.www.plaid_setup import generate_plaid_token

    status = is_plaid_available()
    if not status.get("available"):
        return {"available": False, "url": None}
    token = generate_plaid_token(_value(customer, "name"))
    url = frappe.utils.get_url(
        f"/plaid-setup?customer={quote(_value(customer, 'name'))}&token={quote(token)}"
    )
    return {"available": True, "url": url}


@frappe.whitelist()
def start_signature(signature_request):
    """Generate an embedded DocuSign URL for an owned signature request."""
    customer = get_current_dealer_customer()
    name = _value(customer, "name")
    if not frappe.db.exists("Signature Request", {"name": signature_request, "customer": name}):
        _deny("That signature request is not available in your dealer account.")
    sig_req = frappe.get_doc("Signature Request", signature_request, check_permission=False)
    if _value(sig_req, "status") != "Sent":
        _deny("That document is not currently waiting for your signature.")
    if not _value(sig_req, "envelope_id"):
        _deny("That signature request is missing its DocuSign envelope.")
    if not _value(customer, "email_id"):
        _deny("Your dealer account needs an email address before signing.")
    from dcr.api.docusign import DocuSignClient

    client = DocuSignClient()
    return_url = frappe.utils.get_url(
        "/api/method/dcr.api.dealer_portal.signature_complete"
        f"?signature_request={quote(signature_request)}"
    )
    url = client.get_signing_url(
        envelope_id=_value(sig_req, "envelope_id"),
        email=_value(customer, "email_id"),
        name=_value(customer, "customer_name") or name,
        client_user_id=f"{name}-{_value(sig_req, 'document_type')}",
        return_url=return_url,
    )
    return {"url": url}


@frappe.whitelist()
def signature_complete(signature_request):
    """Finalize an embedded signing return and send the user back to the portal."""
    customer = get_current_dealer_customer()
    name = _value(customer, "name")
    if not frappe.db.exists("Signature Request", {"name": signature_request, "customer": name}):
        _deny("That signature request is not available in your dealer account.")
    sig_req = frappe.get_doc("Signature Request", signature_request, check_permission=False)
    if _value(sig_req, "status") != "Signed":
        if not _value(sig_req, "envelope_id"):
            _deny("That signature request is missing its DocuSign envelope.")
        from dcr.api.docusign import DocuSignClient, _handle_envelope_completed

        client = DocuSignClient()
        if client.get_envelope_status(_value(sig_req, "envelope_id")) == "completed":
            _handle_envelope_completed(_value(sig_req, "envelope_id"), {"status": "completed"})
            frappe.db.commit()
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = frappe.utils.get_url("/portal?signature=complete")
