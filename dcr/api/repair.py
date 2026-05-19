import json

import frappe


def _chart_ref(block):
    data = (block or {}).get("data") or {}
    return data.get("chart_name") or data.get("name")


def _card_ref(block):
    data = (block or {}).get("data") or {}
    return data.get("number_card_name") or data.get("number_card") or data.get("name")


@frappe.whitelist()
def purge_orphan_workspace_refs(dry_run=1):
    """Remove references to deleted Dashboard Charts / Number Cards from Workspaces.

    Workspace render breaks when `content` blocks reference a chart/card that
    no longer exists (negative SVG rect widths, infinite retry). This cleans
    both the `content` JSON and the child tables.

    Pass dry_run=0 to actually save.
    """
    if not frappe.has_permission("Workspace", "write"):
        frappe.throw("Not permitted")
    return _purge_orphan_workspace_refs(
        dry_run=str(dry_run) not in ("0", "false", "False", "")
    )


def _purge_orphan_workspace_refs(dry_run=False):
    """Internal entry point — no permission check. Called from `after_migrate`
    so deploys auto-heal workspaces that ERPNext's `sync_fixtures` restores
    with refs to charts/cards we have since deleted."""
    charts = set(frappe.get_all("Dashboard Chart", pluck="name"))
    cards = set(frappe.get_all("Number Card", pluck="name"))

    report = []

    for ws_name in frappe.get_all("Workspace", pluck="name"):
        doc = frappe.get_doc("Workspace", ws_name)
        actions = []

        # --- child tables ---
        kept_charts = []
        for row in doc.get("charts") or []:
            if row.chart_name and row.chart_name not in charts:
                actions.append({"kind": "chart-row", "ref": row.chart_name})
            else:
                kept_charts.append(row)
        kept_cards = []
        for row in doc.get("number_cards") or []:
            ref = getattr(row, "number_card", None) or getattr(row, "number_card_name", None)
            if ref and ref not in cards:
                actions.append({"kind": "card-row", "ref": ref})
            else:
                kept_cards.append(row)

        # --- content JSON ---
        try:
            content = json.loads(doc.content or "[]")
        except Exception:
            content = []
        kept_blocks = []
        for b in content:
            t = (b or {}).get("type")
            if t == "chart":
                ref = _chart_ref(b)
                if ref and ref not in charts:
                    actions.append({"kind": "chart-content", "ref": ref})
                    continue
            elif t == "number_card":
                ref = _card_ref(b)
                if ref and ref not in cards:
                    actions.append({"kind": "card-content", "ref": ref})
                    continue
            kept_blocks.append(b)

        if not actions:
            continue

        report.append({"workspace": ws_name, "actions": actions})

        if not dry_run:
            # `doc.save()` runs Workspace.validate(), which in v16 rejects
            # writes that remove linked cards/charts (raises ValidationError →
            # HTTP 417). Bypass it: content is a single field (db.set_value),
            # and child-table rows are removed directly. This matches what
            # we did from the desk console manually.
            frappe.db.set_value(
                "Workspace", ws_name, "content", json.dumps(kept_blocks),
                update_modified=True,
            )
            keep_chart_rows = {row.name for row in kept_charts if getattr(row, "name", None)}
            for row in (doc.get("charts") or []):
                if row.name and row.name not in keep_chart_rows:
                    frappe.db.delete("Workspace Chart", {"name": row.name})
            keep_card_rows = {row.name for row in kept_cards if getattr(row, "name", None)}
            for row in (doc.get("number_cards") or []):
                if row.name and row.name not in keep_card_rows:
                    frappe.db.delete("Workspace Number Card", {"name": row.name})
            frappe.clear_document_cache("Workspace", ws_name)

    if not dry_run:
        frappe.db.commit()
        frappe.clear_cache()

    return {"dry_run": dry_run, "report": report}
