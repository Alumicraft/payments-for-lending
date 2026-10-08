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
         "in_list_view": 1, "in_standard_filter": 1, "no_copy": 1},
    ]
    for field in fields:
        if not frappe.db.exists("DocType", field["dt"]):
            continue
        if frappe.get_meta(field["dt"]).has_field(field["fieldname"]):
            continue
        frappe.get_doc({"doctype": "Custom Field", **field}).insert(ignore_permissions=True)
        frappe.clear_cache(doctype=field["dt"])


def populate_purchase_order_dealer(doc, method=None):
    """Keep new and edited orders aligned with their linked home request."""
    if not frappe.get_meta("Purchase Order").has_field("custom_dcr_dealer"):
        return
    hbr = doc.get("custom_home_build_request")
    doc.custom_dcr_dealer = frappe.db.get_value("Home Build Request", hbr, "customer") if hbr else None
