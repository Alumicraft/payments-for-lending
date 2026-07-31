"""Synchronize HBR order and loan stages from source documents."""

try:
    import frappe
except ModuleNotFoundError:
    frappe = None


ORDER_STAGE_FIELD = "custom_order_stage"
LOAN_STAGE_FIELD = "custom_loan_stage"

LOAN_CLOSED_STATUSES = {"Closed", "Settled", "Paid Off", "Completed"}
LOAN_ACTIVE_STATUSES = {"Active"}
LOAN_FUNDED_STATUSES = {"Disbursed", "Partially Disbursed"}
LOAN_APPROVED_STATUSES = {"Approved", "Sanctioned"}
APPLICATION_APPROVED_STATUSES = {"Approved", "Sanctioned"}


def derive_order_stage(
    financing_type,
    has_submitted_po,
    has_submitted_pr,
    has_closed_loan,
    current_order_stage=None,
):
    """Return the HBR kanban stage from operational evidence."""
    if has_submitted_pr:
        if financing_type == "Floored" and has_closed_loan:
            return "Closed"
        if financing_type != "Floored" and current_order_stage == "Closed":
            return "Closed"
        return "Delivered"
    if has_submitted_po:
        return "Ordered"
    return "Pending"


def derive_loan_stage(financing_type, loan_application_status=None, loan_status=None):
    """Return the HBR loan-stage badge from Lending state."""
    if financing_type == "Cash":
        return "Not Applicable"

    if loan_status in LOAN_CLOSED_STATUSES:
        return "Closed"
    if loan_status in LOAN_ACTIVE_STATUSES:
        return "Active"
    if loan_status in LOAN_FUNDED_STATUSES:
        return "Funded"
    if loan_status in LOAN_APPROVED_STATUSES:
        return "Approved"
    if loan_application_status in APPLICATION_APPROVED_STATUSES:
        return "Approved"
    if loan_application_status:
        return "Applied"
    return "Not Started"


def sync_from_doc(doc, method=None):
    """Doc-event entrypoint for documents linked to an HBR."""
    hbr_name = _hbr_from_doc(doc)
    if not hbr_name:
        return

    submitted_pr_override = None
    if doc.doctype == "Purchase Receipt" and method == "on_submit":
        # on_submit runs before the receipt's docstatus is visible to a fresh
        # database query, so use the current transaction as authoritative.
        submitted_pr_override = True
    elif doc.doctype == "Purchase Receipt" and method == "on_cancel":
        submitted_pr_override = _has_submitted_purchase_receipt(
            hbr_name,
            exclude_receipt=doc.name,
        )

    _sync_hbr_stages(hbr_name, submitted_pr_override)


@frappe.whitelist()
def sync_hbr_stages(hbr_name):
    """Update HBR custom stage fields if they exist on the site."""
    return _sync_hbr_stages(hbr_name)


def _sync_hbr_stages(hbr_name, submitted_pr_override=None):
    if not hbr_name:
        return

    has_order_stage = _has_column("Home Build Request", ORDER_STAGE_FIELD)
    has_loan_stage = _has_column("Home Build Request", LOAN_STAGE_FIELD)
    if not has_order_stage and not has_loan_stage:
        return

    fields = ["financing_type"]
    if has_order_stage:
        fields.append(ORDER_STAGE_FIELD)

    hbr = frappe.db.get_value("Home Build Request", hbr_name, fields, as_dict=True)
    if not hbr:
        return

    loan_status = _latest_loan_status(hbr_name)
    application_status = _latest_loan_application_status(hbr_name)
    updates = {}

    if has_order_stage:
        has_submitted_pr = (
            submitted_pr_override
            if submitted_pr_override is not None
            else _has_submitted_purchase_receipt(hbr_name)
        )
        order_stage = derive_order_stage(
            financing_type=hbr.get("financing_type"),
            has_submitted_po=_has_submitted_purchase_order(hbr_name),
            has_submitted_pr=has_submitted_pr,
            has_closed_loan=loan_status in LOAN_CLOSED_STATUSES,
            current_order_stage=hbr.get(ORDER_STAGE_FIELD),
        )
        if hbr.get(ORDER_STAGE_FIELD) != order_stage:
            updates[ORDER_STAGE_FIELD] = order_stage

    if has_loan_stage:
        loan_stage = derive_loan_stage(
            financing_type=hbr.get("financing_type"),
            loan_application_status=application_status,
            loan_status=loan_status,
        )
        updates[LOAN_STAGE_FIELD] = loan_stage

    if updates:
        frappe.db.set_value(
            "Home Build Request",
            hbr_name,
            updates,
            update_modified=False,
        )


def apply_hbr_stage_defaults(doc):
    """Derive HBR stage values from operational evidence on validate.

    Always recomputes custom_order_stage from PO/PR/loan state so a kanban
    drag to an unsupported column snaps back to the derived value.
    """
    if _doc_has_field(doc, ORDER_STAGE_FIELD):
        has_po = bool(doc.name) and _has_submitted_purchase_order(doc.name)
        has_pr = bool(doc.name) and _has_submitted_purchase_receipt(doc.name)
        loan_status = _latest_loan_status(doc.name) if doc.name else None
        order_stage = derive_order_stage(
            financing_type=doc.get("financing_type"),
            has_submitted_po=has_po,
            has_submitted_pr=has_pr,
            has_closed_loan=loan_status in LOAN_CLOSED_STATUSES,
            current_order_stage=doc.get(ORDER_STAGE_FIELD),
        )
        doc.set(ORDER_STAGE_FIELD, order_stage)

    if not _doc_has_field(doc, LOAN_STAGE_FIELD):
        return

    if doc.get("financing_type") == "Cash":
        doc.set(LOAN_STAGE_FIELD, "Not Applicable")
    elif not doc.get(LOAN_STAGE_FIELD):
        doc.set(LOAN_STAGE_FIELD, "Not Started")


def _hbr_from_doc(doc):
    if doc.doctype in ("Purchase Order", "Purchase Receipt", "Payment Entry"):
        hbr_name = doc.get("custom_home_build_request")
        if hbr_name or doc.doctype != "Purchase Receipt":
            return hbr_name
        return _hbr_from_purchase_receipt_items(doc)
    if doc.doctype == "Purchase Invoice":
        return doc.get("home_build_request")
    if doc.doctype == "Loan":
        return doc.get("home_build_request")
    if doc.doctype == "Loan Application":
        return doc.get("home_build_request")
    if doc.doctype == "Loan Disbursement":
        return doc.get("home_build_request")
    if doc.doctype == "Loan Repayment":
        loan_name = doc.get("against_loan")
        if loan_name:
            return frappe.db.get_value("Loan", loan_name, "home_build_request")
    return None


def _hbr_from_purchase_receipt_items(doc):
    for row in doc.get("items") or []:
        purchase_order = row.get("purchase_order")
        if not purchase_order:
            continue
        hbr_name = frappe.db.get_value(
            "Purchase Order",
            purchase_order,
            "custom_home_build_request",
        )
        if hbr_name:
            return hbr_name
    return None


def _has_column(doctype, fieldname):
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def _has_submitted_purchase_order(hbr_name):
    if not _has_column("Purchase Order", "custom_home_build_request"):
        return False
    return bool(
        frappe.db.exists(
            "Purchase Order",
            {
                "custom_home_build_request": hbr_name,
                "docstatus": 1,
            },
        )
    )


def _has_submitted_purchase_receipt(hbr_name, exclude_receipt=None):
    receipt_filters = {
        "custom_home_build_request": hbr_name,
        "docstatus": 1,
    }
    if exclude_receipt:
        receipt_filters["name"] = ["!=", exclude_receipt]

    if _has_column("Purchase Receipt", "custom_home_build_request") and frappe.db.exists(
        "Purchase Receipt",
        receipt_filters,
    ):
        return True

    if not _has_column("Purchase Order", "custom_home_build_request"):
        return False

    exclude_clause = "AND pr.name != %s" if exclude_receipt else ""
    params = [hbr_name]
    if exclude_receipt:
        params.append(exclude_receipt)

    result = frappe.db.sql(
        """
        SELECT pr.name
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        JOIN `tabPurchase Order` po ON po.name = pri.purchase_order
        WHERE po.custom_home_build_request = %s
          AND pr.docstatus = 1
          {exclude_clause}
        LIMIT 1
        """.format(exclude_clause=exclude_clause),
        tuple(params),
    )
    return bool(result)


def _latest_loan_application_status(hbr_name):
    if not _has_column("Loan Application", "home_build_request"):
        return None
    rows = frappe.get_all(
        "Loan Application",
        filters={"home_build_request": hbr_name, "docstatus": ["!=", 2]},
        fields=["status"],
        order_by="modified desc",
        limit=1,
    )
    return rows[0].get("status") if rows else None


def _latest_loan_status(hbr_name):
    if not _has_column("Loan", "home_build_request"):
        return None
    rows = frappe.get_all(
        "Loan",
        filters={"home_build_request": hbr_name, "docstatus": ["!=", 2]},
        fields=["status"],
        order_by="modified desc",
        limit=1,
    )
    return rows[0].get("status") if rows else None


def _doc_has_field(doc, fieldname):
    meta = getattr(doc, "meta", None)
    if meta and hasattr(meta, "has_field"):
        return bool(meta.has_field(fieldname))
    return hasattr(doc, fieldname)
