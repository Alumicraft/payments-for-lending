import frappe

def execute():
    """Delete orphaned and removed Loan Application custom fields.

    Runs before fixture sync so new fields can be created cleanly.
    Idempotent — skips fields that don't exist.
    """
    fields_to_delete = [
        # Orphans from failed v1 restructure (exist on Cloud, not in fixtures)
        "Loan Application-dcr_documents_section",
        "Loan Application-lending_calculations_section",
        # Fields removed per spec
        "Loan Application-requested_advance_amount",
        "Loan Application-first_autopay_description",
        "Loan Application-custom_projected_investment",
        # Sections/breaks being replaced with new names
        "Loan Application-dcr_lending_section",
        "Loan Application-exhibit_a_section",
        "Loan Application-column_break_exhibit_a",
        "Loan Application-column_break_dcr_lending",
        # May exist from previous deploys (safe to attempt)
        "Loan Application-doc_checklist",
    ]

    for field_name in fields_to_delete:
        if frappe.db.exists("Custom Field", field_name):
            frappe.delete_doc("Custom Field", field_name, force=True)
            print(f"  Deleted: {field_name}")
        else:
            print(f"  Skipped (not found): {field_name}")

    frappe.db.commit()
