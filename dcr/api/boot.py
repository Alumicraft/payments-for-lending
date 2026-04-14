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
	_fix_sidebar_items(bootinfo)


def _fix_sidebar_items(bootinfo):
	"""Fix sidebar item rendering for Frappe v16:
	1. Mark Spacer/Sidebar Item Group as standard (bypass TypeLink guard)
	2. Nest items under Section Breaks (populate nested_items)
	"""
	sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}

	for _name, sidebar in sidebar_items.items():
		items = sidebar.get("items")
		if not items:
			continue

		# Idempotency: skip if already nested
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
				new_items.append(item)

		sidebar["items"] = new_items


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
