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
	"""Mark non-link sidebar item types as standard to bypass the
	TypeLink.make() early-return rendering guard (frappe/frappe#37872).

	The guard skips items without a path unless they are 'standard' or
	type 'Section Break'.  Spacer and Sidebar Item Group items have no
	link_to, so get_path() returns null and the guard kills rendering.

	Note: Section Break nesting is intentionally NOT done here because
	Frappe v16's TypeSectionBreak renderer is broken — it creates zero
	DOM elements even with correctly populated nested_items."""
	sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}

	for _name, sidebar in sidebar_items.items():
		for item in (sidebar.get("items") or []):
			if item.get("type") in ("Sidebar Item Group", "Spacer"):
				item["standard"] = True


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
