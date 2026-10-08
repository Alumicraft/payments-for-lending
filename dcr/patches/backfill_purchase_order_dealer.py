"""Fill missing dealer context without replacing existing values."""
import frappe
from dcr.api.pilot_fields import ensure_pilot_fields


def execute():
    from dcr.setup import ensure_order_hbr_fields
    ensure_order_hbr_fields(only_doctypes=["Purchase Order"])
    ensure_pilot_fields()
    if not (frappe.db.has_column("Purchase Order", "custom_dcr_dealer")
            and frappe.db.has_column("Purchase Order", "custom_home_build_request")):
        return
    frappe.db.sql("""
        UPDATE `tabPurchase Order` po
        INNER JOIN `tabHome Build Request` hbr ON hbr.name = po.custom_home_build_request
        SET po.custom_dcr_dealer = hbr.customer
        WHERE COALESCE(po.custom_dcr_dealer, '') = ''
          AND COALESCE(hbr.customer, '') != ''
    """)
    frappe.db.commit()
