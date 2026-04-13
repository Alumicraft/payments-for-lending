import frappe


def boot_session(bootinfo):
	"""Fix field name mismatch: sidebar renderer reads icon_url but
	Desktop Icon provides logo_url/icon_image."""
	for item in (bootinfo.desktop_icons or []):
		url = item.get("logo_url") or item.get("icon_image")
		if url and not item.get("icon_url"):
			item["icon_url"] = url
		if item.get("icon_url") and item.get("icon"):
			item["icon"] = None

	# Frappe v16 get_sidebar_items() drops Sidebar Item Group and child
	# items from boot data. Restore them from the database before any
	# other processing.
	_restore_missing_sidebar_items(bootinfo)

	# Remove broken workspace sidebar items that have null link_to.
	# These cause TypeError in frappe.router.slug which kills the desktop.
	sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}
	for name, sidebar in sidebar_items.items():
		if sidebar.get("items"):
			sidebar["items"] = [
				item for item in sidebar["items"]
				if item.get("type") != "Link" or item.get("link_to") or item.get("link_type") == "URL"
			]

	# Restructure flat sidebar items into nested structure for v16 renderer
	_nest_sidebar_items(bootinfo)


def _restore_missing_sidebar_items(bootinfo):
	"""Frappe v16 get_sidebar_items() drops Sidebar Item Group and child
	items from boot data. Re-read from the database when items are missing."""
	sidebar_data = getattr(bootinfo, "workspace_sidebar_item", None) or {}
	if not sidebar_data:
		return

	# Internal child-table fields to strip from raw SQL results
	_internal = frozenset({
		"name", "owner", "creation", "modified", "modified_by",
		"parent", "parenttype", "parentfield", "doctype", "docstatus", "idx",
	})

	# Build lookup: lowercase sidebar name → document name (direct SQL)
	name_map = {}
	for row in frappe.db.sql("SELECT name FROM `tabWorkspace Sidebar`", as_dict=True):
		name_map[row.name.lower()] = row.name

	# Item counts per sidebar (direct SQL)
	db_counts = {}
	for row in frappe.db.sql(
		"SELECT parent, COUNT(*) as cnt "
		"FROM `tabWorkspace Sidebar Item` "
		"GROUP BY parent",
		as_dict=True,
	):
		db_counts[row.parent] = row.cnt

	for ws_key, sidebar in sidebar_data.items():
		sidebar_name = name_map.get(ws_key)
		if not sidebar_name:
			sidebar["_dcr_skip"] = "no_name"
			continue

		boot_count = len(sidebar.get("items") or [])
		db_count = db_counts.get(sidebar_name, 0)
		sidebar["_dcr_boot"] = boot_count
		sidebar["_dcr_db"] = db_count

		if db_count <= boot_count:
			sidebar["_dcr_skip"] = "count_ok"
			continue

		# Items were dropped — restore full list via direct SQL
		try:
			raw = frappe.db.sql(
				"SELECT * FROM `tabWorkspace Sidebar Item` "
				"WHERE parent = %s ORDER BY idx",
				sidebar_name,
				as_dict=True,
			)
			sidebar["_dcr_raw"] = len(raw)
			sidebar["items"] = [
				{k: v for k, v in row.items() if k not in _internal}
				for row in raw
			]
			sidebar["_dcr_restored"] = len(sidebar["items"])
		except Exception as e:
			sidebar["_dcr_error"] = str(e)


def _nest_sidebar_items(bootinfo):
	"""Restructure flat sidebar items to nest children under Section Breaks,
	and mark Sidebar Item Group items as standard to bypass the TypeLink.make()
	early-return rendering guard (frappe/frappe#37872, #35881)."""
	sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}

	for _name, sidebar in sidebar_items.items():
		items = sidebar.get("items")
		if not items:
			continue

		# Idempotency: skip if any Section Break already has nested_items populated
		already_nested = any(
			item.get("type") == "Section Break"
			and item.get("nested_items")
			for item in items
		)
		if already_nested:
			continue

		new_items = []
		current_section = None

		for item in items:
			# Mark non-link item types as standard so TypeLink.make()
			# doesn't skip them (the guard exempts standard items).
			# Side effect: hides drag/settings controls in sidebar edit mode.
			if item.get("type") in ("Sidebar Item Group", "Spacer"):
				item["standard"] = True

			if item.get("type") == "Section Break":
				current_section = item
				if not item.get("nested_items"):
					item["nested_items"] = []
				new_items.append(item)
			elif current_section is not None:
				current_section["nested_items"].append(item)
			else:
				# Items before first Section Break stay top-level
				new_items.append(item)

		sidebar["items"] = new_items


@frappe.whitelist()
def debug_sidebar_restore():
	"""Temporary debug endpoint — remove after fixing."""
	name_map = {}
	for row in frappe.db.sql("SELECT name FROM `tabWorkspace Sidebar`", as_dict=True):
		name_map[row.name.lower()] = row.name

	db_counts = {}
	for row in frappe.db.sql(
		"SELECT parent, COUNT(*) as cnt "
		"FROM `tabWorkspace Sidebar Item` "
		"GROUP BY parent",
		as_dict=True,
	):
		db_counts[row.parent] = row.cnt

	sidebar_name = name_map.get("contacts")
	boot_data = getattr(frappe.local, "boot", None)
	boot_count = None
	if boot_data and hasattr(boot_data, "workspace_sidebar_item"):
		ws = boot_data.workspace_sidebar_item.get("contacts", {})
		boot_count = len(ws.get("items", []))

	raw_items = []
	if sidebar_name:
		raw_items = frappe.db.sql(
			"SELECT label, type FROM `tabWorkspace Sidebar Item` "
			"WHERE parent = %s ORDER BY idx",
			sidebar_name,
			as_dict=True,
		)

	return {
		"name_map_has_contacts": "contacts" in name_map,
		"sidebar_name": sidebar_name,
		"db_count": db_counts.get(sidebar_name, "NOT_FOUND") if sidebar_name else "NO_NAME",
		"boot_count": boot_count,
		"raw_items_count": len(raw_items),
		"raw_items": raw_items,
	}


@frappe.whitelist()
def get_layout_with_icons():
	"""Override get_layout to merge icon image data into saved layouts.
	The DesktopLayout saves a JSON snapshot that loses logo_url/icon_image
	fields, so we merge them back from the actual Desktop Icon records."""
	import json

	layout = None
	try:
		doc = frappe.get_doc("Desktop Layout", frappe.session.user)
		if doc.layout:
			layout = json.loads(doc.layout)
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return None

	if not layout:
		return layout

	icons_with_images = frappe.get_all(
		"Desktop Icon",
		filters={"icon_image": ["is", "set"]},
		fields=["label", "logo_url", "icon_image"],
	)
	image_map = {i.label: i for i in icons_with_images}

	for item in layout:
		label = item.get("label")
		if label and label in image_map:
			img = image_map[label]
			if not item.get("logo_url"):
				item["logo_url"] = img.logo_url or img.icon_image
			if not item.get("icon_image"):
				item["icon_image"] = img.icon_image

	return layout
