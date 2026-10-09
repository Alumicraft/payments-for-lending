"""Fields and source mappings for the staff pilot workflow."""
import json

import frappe


def ensure_pilot_fields():
    fields = [
        {"dt": "Loan Application", "fieldname": "monthly_insurance_amount",
         "label": "Monthly Insurance Amount", "fieldtype": "Currency",
         "insert_after": "repayment_amount", "non_negative": 1,
         "description": "Staff-entered monthly insurance amount for the Flooring Packet."},
        {"dt": "Purchase Order", "fieldname": "custom_dcr_dealer",
         "label": "Dealer", "fieldtype": "Link", "options": "Customer",
         "insert_after": "custom_home_build_request", "read_only": 1,
         "fetch_from": "custom_home_build_request.customer",
         "in_list_view": 1, "in_standard_filter": 1, "no_copy": 1},
    ]
    for field in fields:
        if not frappe.db.exists("DocType", field["dt"]):
            continue
        if frappe.get_meta(field["dt"]).has_field(field["fieldname"]):
            continue
        frappe.get_doc({"doctype": "Custom Field", **field}).insert(ignore_permissions=True)
        frappe.clear_cache(doctype=field["dt"])


def ensure_purchase_order_form_layout():
    """Keep DCR's request context in the first PO section, not Connections.

    Change only the three DCR field positions and the app-owned dealer's fetch
    rule. A saved field_order takes precedence over insert_after in Frappe, so
    move this context there too while preserving every other field's order.
    """
    placements = {
        "custom_home_build_request": "supplier_section",
        "custom_dcr_dealer": "custom_home_build_request",
        "custom_payment_type": "custom_dcr_dealer",
    }
    changed = False
    available = []
    for fieldname, insert_after in placements.items():
        name = frappe.db.exists("Custom Field", {"dt": "Purchase Order", "fieldname": fieldname})
        if not name:
            continue
        available.append(fieldname)
        field = frappe.get_doc("Custom Field", name)
        updates = {"insert_after": insert_after}
        if fieldname == "custom_dcr_dealer":
            updates["fetch_from"] = "custom_home_build_request.customer"
        dirty = False
        for property_name, value in updates.items():
            if field.get(property_name) != value:
                field.set(property_name, value)
                dirty = True
        if dirty:
            field.save(ignore_permissions=True)
            changed = True
    if available:
        for row in frappe.get_all("Property Setter", filters={
            "doc_type": "Purchase Order", "doctype_or_field": "DocType", "property": "field_order",
        }, fields=["name"]):
            setter = frappe.get_doc("Property Setter", row.name)
            order = json.loads(setter.value)
            if not isinstance(order, list) or "supplier_section" not in order:
                continue
            revised = [name for name in order if name not in available]
            start = revised.index("supplier_section") + 1
            revised[start:start] = available
            if revised != order:
                setter.value = json.dumps(revised)
                setter.save(ignore_permissions=True)
                changed = True
    if changed:
        frappe.clear_cache(doctype="Purchase Order")


def ensure_loan_application_insurance_layout():
    """Make insurance available beside the monthly payment on every draft.

    Older sites placed this field inside the conditional Deal Projections
    section. Preserve its values and field rules; change only its position.
    """
    doctype = "Loan Application"
    fieldname = "monthly_insurance_amount"
    anchor = "repayment_amount"
    name = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
    if not name or not frappe.get_meta(doctype).has_field(anchor):
        return
    changed = False
    field = frappe.get_doc("Custom Field", name)
    if field.get("insert_after") != anchor:
        field.set("insert_after", anchor)
        field.save(ignore_permissions=True)
        changed = True
    for row in frappe.get_all("Property Setter", filters={
        "doc_type": doctype, "doctype_or_field": "DocType", "property": "field_order",
    }, fields=["name"]):
        setter = frappe.get_doc("Property Setter", row.name)
        order = json.loads(setter.value)
        if not isinstance(order, list) or anchor not in order:
            continue
        revised = [value for value in order if value != fieldname]
        revised.insert(revised.index(anchor) + 1, fieldname)
        if revised != order:
            setter.value = json.dumps(revised)
            setter.save(ignore_permissions=True)
            changed = True
    if changed:
        frappe.clear_cache(doctype=doctype)


def ensure_loan_payment_layout():
    """Repair the known Loan override that traps monthly payment in credit limits.

    Move only the existing currency field, preserving all other site positions.
    Other layouts, invalid overrides and missing anchors remain untouched.
    """
    doctype = "Loan"
    fieldname = "monthly_repayment_amount"
    anchor = "rate_of_interest"
    if not frappe.db.exists("DocType", doctype):
        return
    meta = frappe.get_meta(doctype)
    fields = {df.fieldname: df for df in meta.fields}
    field = fields.get(fieldname)
    destination = fields.get("section_break_8")
    if (not field or field.fieldtype != "Currency" or anchor not in fields
            or not destination or destination.fieldtype != "Section Break"
            or getattr(destination, "hidden", 0) or getattr(destination, "depends_on", None)):
        return

    def section_for(order, name):
        for value in reversed(order[:order.index(name)]):
            df = fields.get(value)
            if df and df.fieldtype in ("Section Break", "Tab Break"):
                return value
        return None

    changed = False
    for row in frappe.get_all("Property Setter", filters={
        "doc_type": doctype, "doctype_or_field": "DocType", "property": "field_order",
    }, fields=["name"]):
        setter = frappe.get_doc("Property Setter", row.name)
        try:
            order = json.loads(setter.value)
        except (ValueError, TypeError):
            continue
        if not isinstance(order, list) or not all(isinstance(value, str) for value in order):
            continue
        if order.count(fieldname) != 1 or order.count(anchor) != 1:
            continue
        if (section_for(order, fieldname) != "loan_credit_limits_section"
                or section_for(order, anchor) != "section_break_8"):
            continue
        revised = [value for value in order if value != fieldname]
        revised.insert(revised.index(anchor) + 1, fieldname)
        setter.value = json.dumps(revised)
        setter.save(ignore_permissions=True)
        changed = True
    if changed:
        frappe.clear_cache(doctype=doctype)


def populate_purchase_order_dealer(doc, method=None):
    """Keep new and edited orders aligned with their linked home request."""
    if not frappe.get_meta("Purchase Order").has_field("custom_dcr_dealer"):
        return
    hbr = doc.get("custom_home_build_request")
    doc.custom_dcr_dealer = frappe.db.get_value("Home Build Request", hbr, "customer") if hbr else None
