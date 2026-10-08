"""Fields and source mappings for the staff pilot workflow."""
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
    rule. Native field order, site validation, and other custom fields remain
    under their existing configuration.
    """
    placements = {
        "custom_home_build_request": "supplier_section",
        "custom_dcr_dealer": "custom_home_build_request",
        "custom_payment_type": "custom_dcr_dealer",
    }
    changed = False
    for fieldname, insert_after in placements.items():
        name = frappe.db.exists("Custom Field", {"dt": "Purchase Order", "fieldname": fieldname})
        if not name:
            continue
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
    if changed:
        frappe.clear_cache(doctype="Purchase Order")


def populate_purchase_order_dealer(doc, method=None):
    """Keep new and edited orders aligned with their linked home request."""
    if not frappe.get_meta("Purchase Order").has_field("custom_dcr_dealer"):
        return
    hbr = doc.get("custom_home_build_request")
    doc.custom_dcr_dealer = frappe.db.get_value("Home Build Request", hbr, "customer") if hbr else None
