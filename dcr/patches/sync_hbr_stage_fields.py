import frappe


def execute():
    """Backfill derived HBR stage fields for existing deals."""
    from dcr.setup import ensure_hbr_stage_field_options
    from dcr.api.hbr_stage import sync_hbr_stages

    ensure_hbr_stage_field_options()

    for hbr_name in frappe.get_all("Home Build Request", pluck="name"):
        sync_hbr_stages(hbr_name)

    frappe.db.commit()
