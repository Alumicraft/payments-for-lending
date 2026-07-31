import frappe

from dcr.setup import ensure_factory_addresses, ensure_supplier_geo_fields


def execute():
    ensure_supplier_geo_fields()
    ensure_factory_addresses()
    frappe.db.commit()
