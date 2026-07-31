import frappe

from dcr.setup import submit_imported_factory_assignments


def execute():
    submit_imported_factory_assignments()
    frappe.db.commit()
