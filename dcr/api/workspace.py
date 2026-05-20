"""Workspace overrides for Frappe desk customization saves."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.desk.desktop import save_new_widget
from frappe.desk.doctype.workspace.workspace import is_workspace_manager


def _chart_ref(block):
	data = (block or {}).get("data") or {}
	return data.get("chart_name") or data.get("name")


def _card_ref(block):
	data = (block or {}).get("data") or {}
	return data.get("number_card_name") or data.get("number_card") or data.get("name")


def _can_save_workspace(doc):
	if doc.public:
		return is_workspace_manager()
	if doc.for_user == frappe.session.user:
		return True
	return is_workspace_manager()


def _strip_orphan_chart_card_blocks(doc, blocks):
	"""Drop chart/card blocks whose linked records no longer exist.

	Frappe validates Workspace child-table Link fields during save. If a
	workspace still contains a deleted Dashboard Chart or Number Card, the
	save fails after the client has already switched to the loading skeleton.
	"""
	try:
		content = json.loads(blocks or "[]")
	except Exception:
		return blocks

	if not isinstance(content, list):
		return blocks

	charts = set(frappe.get_all("Dashboard Chart", pluck="name"))
	cards = set(frappe.get_all("Number Card", pluck="name"))
	kept = []
	removed = []

	for block in content:
		block_type = (block or {}).get("type")
		if block_type == "chart":
			ref = _chart_ref(block)
			if ref and ref not in charts:
				removed.append({"kind": "chart", "ref": ref})
				continue
		elif block_type == "number_card":
			ref = _card_ref(block)
			if ref and ref not in cards:
				removed.append({"kind": "number_card", "ref": ref})
				continue
		kept.append(block)

	if not removed:
		return blocks

	frappe.log_error(
		json.dumps({"workspace": doc.name, "removed": removed}, indent=2),
		"Removed orphan Workspace blocks before save",
	)
	return json.dumps(kept)


@frappe.whitelist()
def save_page(name, public, new_widgets, blocks):
	"""Save a Workspace from the desk editor without leaving the skeleton stuck.

	This replaces Frappe v16's `save_page` guard, which can return no message for
	public workspaces. The client only clears its loading skeleton when a message
	is returned, so a silent `None` response looks like an infinite load.
	"""
	public = frappe.parse_json(public)
	doc = frappe.get_doc("Workspace", name)

	if not _can_save_workspace(doc):
		frappe.throw(_("Not permitted to save this workspace"), frappe.PermissionError)

	if not doc.type:
		doc.type = "Workspace"

	blocks = _strip_orphan_chart_card_blocks(doc, blocks)
	doc.content = blocks
	save_new_widget(doc, name, blocks, new_widgets)
	frappe.clear_document_cache("Workspace", name)
	frappe.clear_cache()

	return {"name": name, "public": public, "label": doc.label}
