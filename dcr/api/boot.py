import frappe

# Fallback for after_migrate not firing on Frappe Cloud deploys. We run these
# dcr.setup syncs once per worker process so restarted workers can repair stale
# site config even when hooks are skipped. Names must match functions in
# dcr.setup; each runs at most once per worker (tracked in _BOOT_SYNCS_DONE).
_BOOT_SYNCS = (
	"ensure_map_block",
	"ensure_loan_demand_offset_order",
	"ensure_lending_accounting_defaults",
)
_BOOT_SYNCS_DONE = set()


def _run_boot_syncs():
	import dcr.setup as setup
	for fn_name in _BOOT_SYNCS:
		if fn_name in _BOOT_SYNCS_DONE:
			continue
		try:
			getattr(setup, fn_name)()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{fn_name} (boot_session)")
		finally:
			# Mark done even on failure so a broken worker doesn't retry every session.
			_BOOT_SYNCS_DONE.add(fn_name)


def boot_session(bootinfo):
	"""Fix field name mismatch: sidebar renderer reads icon_url but
	Desktop Icon provides logo_url/icon_image."""
	_run_boot_syncs()

	for item in (bootinfo.desktop_icons or []):
		url = item.get("logo_url") or item.get("icon_image")
		if url and not item.get("icon_url"):
			item["icon_url"] = url
		if item.get("icon_url") and item.get("icon"):
			item["icon"] = None

	sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}
	for _name, sidebar in sidebar_items.items():
		# Remove broken workspace sidebar items that have null link_to.
		# These cause TypeError in frappe.router.slug which kills the desktop.
		if sidebar.get("items"):
			sidebar["items"] = [
				item for item in sidebar["items"]
				if item.get("type") != "Link" or item.get("link_to") or item.get("link_type") == "URL"
			]

		# Fix sidebar item rendering quirks:
		# - Spacer: needs standard=True to bypass TypeLink.make() guard
		# - Section Break: needs indent=1 for icon+label style (vs bare divider)
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
