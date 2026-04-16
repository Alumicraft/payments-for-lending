import frappe

# Fallback for after_migrate not firing on Frappe Cloud deploys. We run the
# block sync once per worker process — cheap when the block is already current,
# and guarantees the desk reflects the latest setup.py after a deploy restarts
# the workers.
_MAP_BLOCK_SYNCED = False


def boot_session(bootinfo):
	"""Fix field name mismatch: sidebar renderer reads icon_url but
	Desktop Icon provides logo_url/icon_image."""
	global _MAP_BLOCK_SYNCED
	if not _MAP_BLOCK_SYNCED:
		try:
			from dcr.setup import ensure_map_block
			ensure_map_block()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ensure_map_block (boot_session)")
		finally:
			# Set even on failure so we don't retry every session on a broken worker.
			_MAP_BLOCK_SYNCED = True

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

	# Fix sidebar item rendering quirks:
	# - Spacer: needs standard=True to bypass TypeLink.make() guard
	# - Section Break: needs indent=1 for icon+label style (vs bare divider)
	sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}
	for _name, sidebar in sidebar_items.items():
		for item in (sidebar.get("items") or []):
			if item.get("type") == "Spacer":
				item["standard"] = True
			if item.get("type") == "Section Break" and not item.get("indent"):
				item["indent"] = 1

	# Note: sidebar Section Breaks and dropdowns are handled by config, not code.
	# Use Section Break type with a label + Child Item checked on children.
	# See Workspace Sidebar > Selling for the correct pattern.



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
