"""
Retire ACH Authorization doctype — hide from creation while preserving data.

Removes all create/write permissions so no new records can be made.
Existing data remains readable for audit.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "ACH Authorization"):
        return

    # Remove create and write permissions for all roles
    frappe.db.sql("""
        UPDATE `tabDocPerm`
        SET `create` = 0, `write` = 0, `delete` = 0
        WHERE parent = 'ACH Authorization'
    """)

    # Clear the cache so permission changes take effect
    frappe.clear_cache(doctype="ACH Authorization")

    frappe.logger().info("ACH Authorization doctype retired — create/write/delete permissions removed")
    print("ACH Authorization doctype retired — create/write/delete permissions removed")
