# Frappe v16 Sidebar Fix — Portable Implementation Spec

**Date:** 2026-04-27
**Status:** Ready for implementation
**Target:** Any Frappe v16 custom app on Frappe Cloud

A self-contained spec to fix Frappe v16 workspace sidebar bugs in any custom Frappe app. Apply this to your custom app once, configure your workspaces correctly, and the sidebar will work like the standard ERPNext workspaces.

## What This Fixes

| Bug | Symptom | Fix |
|-----|---------|-----|
| Spacer items invisible | Configured spacers don't render between items | `boot.py` marks them `standard: true` to bypass TypeLink guard |
| Section Break wrong style | Custom Section Breaks render as bare divider instead of icon+label dropdown | `boot.py` sets `indent: 1`; UI must check Indent on Section Break |
| Sidebar Item Group label missing | Group renders with bare chevron, no label | **Don't use Sidebar Item Group** — use Section Break with label instead (Sidebar Item Group is broken in v16) |
| Filter field ignored | Sidebar items with `filters` set don't apply them when clicked | `sidebar_fix.js` reads `filters` field, sets `frappe.route_options` before navigation |
| Wrong active state | When 2+ items link to same DocType, wrong one highlights | `sidebar_fix.js` polls and corrects `.active-sidebar` class on `.standard-sidebar-item` |
| Workspace switching | Navigating to a DocType yanks user to a different workspace | `sidebar_fix.js` patches `set_workspace_sidebar` to keep current workspace |
| Hard-refresh wrong workspace | Reloading a DocType view lands on a different workspace | `sidebar_fix.js` picks workspace based on which one lists the doctype, preferring last-used |

## Prerequisites

- Frappe Framework v16
- A custom Frappe app (referred to as `<app_name>` below)
- Frappe Cloud deployment (or any Frappe v16 environment)
- Existing `boot_session` hook is allowed but not required

## Verified DOM Selectors (Frappe v16)

These were the wrong selectors that wasted hours of debugging — use these:

| Element | Correct Selector | Wrong Selector (Don't Use) |
|---------|------------------|---------------------------|
| Sidebar container | `.body-sidebar-container` | `.workspace-sidebar` |
| Workspace name attribute | `.body-sidebar[data-title]` | `[data-workspace]` |
| Item container | `.sidebar-item-container` | (correct as-is) |
| Item anchor (clickable) | `.item-anchor` | `.standard-sidebar-item` (parent only) |
| Item label text | `.sidebar-item-label` | (correct as-is) |
| Active state class | `.active-sidebar` | `.active` |
| Active state target element | `.standard-sidebar-item` | `.sidebar-item-container` |

## Implementation

### Part 1: Configuration (UI, no code)

This part must be done manually in each Workspace Sidebar that should have a dropdown. Do NOT use Sidebar Item Group — it's broken in v16.

For each workspace sidebar that needs a dropdown section:

1. Go to `/app/workspace-sidebar/<workspace_name>` (e.g., `Contacts`)
2. Add a row with `Type: Section Break` and a `Label` (this becomes the dropdown header)
3. Click the edit pencil on the Section Break row → **check Indent** → save
4. (Optional) Set an icon on the Section Break row (e.g., "book", "database", "users")
5. For items that should be inside the dropdown: **check Child Item** ✓ on each row
6. Save the workspace sidebar

**Verification:** Compare your config to a working standard workspace like `/app/workspace-sidebar/Selling`. The Section Break for "Setup" or "Reports" should have Indent checked and the items below it should have Child Item checked.

### Part 2: boot.py Changes

Add a `boot_session` hook (or extend your existing one) in `<app_name>/api/boot.py`:

```python
import frappe


def boot_session(bootinfo):
    """Fix Frappe v16 sidebar rendering quirks."""

    # 1. Remove broken sidebar items with null link_to.
    # These cause TypeError in frappe.router.slug which kills the desk.
    sidebar_items = getattr(bootinfo, "workspace_sidebar_item", None) or {}
    for name, sidebar in sidebar_items.items():
        if sidebar.get("items"):
            sidebar["items"] = [
                item for item in sidebar["items"]
                if item.get("type") != "Link"
                or item.get("link_to")
                or item.get("link_type") == "URL"
            ]

    # 2. Fix sidebar item rendering quirks:
    # - Spacer: needs standard=True to bypass TypeLink.make() early-return guard
    # - Section Break: needs indent=1 for icon+label style (vs bare divider)
    for _name, sidebar in sidebar_items.items():
        for item in (sidebar.get("items") or []):
            if item.get("type") == "Spacer":
                item["standard"] = True
            if item.get("type") == "Section Break" and not item.get("indent"):
                item["indent"] = 1
```

If your app already has a `boot_session` function, merge these two blocks into the existing one.

### Part 3: hooks.py

Register the boot hook and JS file in `<app_name>/hooks.py`:

```python
boot_session = "<app_name>.api.boot.boot_session"
app_include_js = ["/assets/<app_name>/js/sidebar_fix.js"]
```

If `app_include_js` already exists, add `sidebar_fix.js` to the list:

```python
app_include_js = [
    "/assets/<app_name>/js/existing_file.js",
    "/assets/<app_name>/js/sidebar_fix.js",
]
```

### Part 4: sidebar_fix.js

Create `<app_name>/public/js/sidebar_fix.js` with this complete content:

```javascript
/**
 * Frappe v16 Sidebar Fix
 *
 * 1. Applies sidebar item filters as frappe.route_options on click
 *    (Frappe ignores the `filters` field during navigation)
 * 2. Corrects active-state highlighting for duplicate-doctype items
 * 3. Prevents unwanted workspace switching when navigating to a DocType
 *    that lives in another module's workspace
 * 4. On hard-refresh, picks the correct workspace based on which sidebar
 *    actually lists the current doctype (preferring last-used)
 */
(function () {
	"use strict";

	var _initialized = false;
	var _last_clicked = null;

	// ── Helpers ────────────────────────────────────────────────────────

	function parse_filters(str) {
		if (!str) return [];
		try { var r = JSON.parse(str); return Array.isArray(r) ? r : []; }
		catch (e) { return []; }
	}

	function get_workspace_name() {
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.current_workspace) {
			return frappe.app.sidebar.current_workspace;
		}
		var el = document.querySelector(".body-sidebar[data-title]");
		if (el) return el.getAttribute("data-title").toLowerCase();
		return null;
	}

	function get_all_items() {
		var ws = get_workspace_name();
		if (!ws) return [];
		var data = (frappe.boot.workspace_sidebar_item || {})[ws];
		if (!data || !data.items) return [];
		// Flatten top-level + nested items
		var all = [];
		for (var i = 0; i < data.items.length; i++) {
			all.push(data.items[i]);
			var nested = data.items[i].nested_items || [];
			for (var j = 0; j < nested.length; j++) all.push(nested[j]);
		}
		return all;
	}

	function set_active(container) {
		// Frappe v16 uses .active-sidebar on .standard-sidebar-item
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return;
		var all = sb.querySelectorAll(".standard-sidebar-item");
		for (var i = 0; i < all.length; i++) all[i].classList.remove("active-sidebar");
		var target = container.querySelector(".standard-sidebar-item") || container;
		target.classList.add("active-sidebar");
	}

	function find_dom_by_label(label) {
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return null;
		var els = sb.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < els.length; i++) {
			var lbl = els[i].querySelector(".sidebar-item-label");
			if (lbl && lbl.textContent.trim() === label) return els[i];
		}
		return null;
	}

	// ── Click handler (capture phase) ──────────────────────────────────

	function on_click(e) {
		var container = e.target.closest(".sidebar-item-container");
		if (!container) return;
		var lbl_el = container.querySelector(".sidebar-item-label");
		if (!lbl_el) return;
		var label = lbl_el.textContent.trim();

		var items = get_all_items();
		var item = null;
		for (var i = 0; i < items.length; i++) {
			if (items[i].label === label) { item = items[i]; break; }
		}
		if (!item || item.type !== "Link") return;

		// Apply filters as route_options before Frappe navigates
		if (item.filters) {
			var filters = parse_filters(item.filters);
			if (filters.length) {
				var opts = {};
				for (var i = 0; i < filters.length; i++) {
					var f = filters[i];
					opts[f[1]] = f[2] === "=" ? f[3] : [f[2], f[3]];
				}
				frappe.route_options = opts;
			}
		}

		// Track click — poll every 200ms for 5s to enforce active state
		// (Frappe rebuilds sidebar DOM during nav; MutationObserver alone fails)
		_last_clicked = { label: label, link_to: item.link_to };
		var _attempts = 0;
		var _poll = setInterval(function () {
			_attempts++;
			if (_attempts > 25 || !_last_clicked) { clearInterval(_poll); return; }
			var el = find_dom_by_label(_last_clicked.label);
			if (!el) return;
			var inner = el.querySelector(".standard-sidebar-item");
			if (inner && !inner.classList.contains("active-sidebar")) {
				set_active(el);
			}
		}, 200);
		setTimeout(function () { _last_clicked = null; }, 5000);
	}

	// ── Active state on route change ───────────────────────────────────

	function fix_active() {
		if (_last_clicked) {
			var dt = (typeof cur_list !== "undefined" && cur_list) ? cur_list.doctype : null;
			if (dt && dt === _last_clicked.link_to) {
				var el = find_dom_by_label(_last_clicked.label);
				if (el) { set_active(el); return; }
			}
			_last_clicked = null;
		}

		if (typeof cur_list === "undefined" || !cur_list || !cur_list.doctype) return;
		var items = get_all_items();
		var matches = [];
		for (var i = 0; i < items.length; i++) {
			if (items[i].type === "Link" && items[i].link_to === cur_list.doctype)
				matches.push(items[i]);
		}
		if (matches.length <= 1) return;

		var cur_filters = [];
		try { cur_filters = cur_list.filter_area.get(); } catch (e) { return; }

		var best = null, best_score = -1;
		for (var i = 0; i < matches.length; i++) {
			var mf = parse_filters(matches[i].filters);
			if (!mf.length && !cur_filters.length) {
				if (0 > best_score) { best_score = 0; best = matches[i]; }
				continue;
			}
			if (!mf.length) continue;
			var score = 0, ok = true;
			for (var j = 0; j < mf.length; j++) {
				var f = mf[j], found = false;
				for (var k = 0; k < cur_filters.length; k++) {
					var cf = cur_filters[k];
					if (cf[1] === f[1] && cf[2] === f[2] && String(cf[3]) === String(f[3]))
					{ found = true; break; }
				}
				if (found) score++; else { ok = false; break; }
			}
			if (ok && score > best_score) { best_score = score; best = matches[i]; }
		}
		if (best) {
			var el = find_dom_by_label(best.label);
			if (el) set_active(el);
		}
	}

	function fix_active_retry(n) {
		if (n <= 0) return;
		if (typeof cur_list !== "undefined" && cur_list && cur_list.filter_area) fix_active();
		else setTimeout(function () { fix_active_retry(n - 1); }, 200);
	}

	// ── Prevent unwanted workspace switching ───────────────────────────
	// Frappe's set_workspace_sidebar uses URL slugs (e.g. "home-build-request")
	// to look up sidebars by `link_to` (e.g. "Home Build Request"). The slug
	// match never fires, so it falls through to module-based switching.
	// Patch it to only run that logic when explicitly navigating to a workspace.

	function patch_workspace_switch() {
		if (!frappe.app || !frappe.app.sidebar) return false;
		var sb = frappe.app.sidebar;
		if (sb._sidebar_fix_patched) return true;
		if (typeof sb.set_workspace_sidebar !== "function") return false;
		if (typeof sb.setup !== "function") return false;

		var original = sb.set_workspace_sidebar.bind(sb);
		var original_setup = sb.setup.bind(sb);

		sb.set_workspace_sidebar = function (router) {
			try {
				var route = frappe.get_route() || [];
				var map = frappe.boot.workspace_sidebar_item || {};
				var slug = "";

				if (route.length === 1) {
					slug = (route[0] || "").toLowerCase();
				} else if (route.length >= 2 && (route[0] || "").toLowerCase() === "workspaces") {
					return original(router);
				}

				var is_workspace_nav = slug && !!map[slug];

				if (is_workspace_nav || !sb.sidebar_title) {
					return original(router);
				}

				// Otherwise keep the user on their current workspace —
				// just refresh which sidebar item is highlighted.
				sb.set_active_workspace_item();
			} catch (e) {
				console.log("Sidebar fix patch error:", e);
				return original(router);
			}
		};

		// Safety net: Frappe also invokes sidebar.setup(workspace) from
		// other paths. If any fire during a doctype navigation, block the
		// rebuild and just refresh highlighting instead.
		sb.setup = function (workspace_title) {
			try {
				var route = frappe.get_route() || [];
				var is_doctype_view =
					route.indexOf("List") !== -1 ||
					route.indexOf("Form") !== -1 ||
					route.indexOf("query-report") !== -1 ||
					route.indexOf("dashboard-view") !== -1 ||
					route.indexOf("Tree") !== -1;

				if (is_doctype_view && sb.sidebar_title &&
					workspace_title !== sb.sidebar_title) {
					if (typeof sb.set_active_workspace_item === "function") {
						sb.set_active_workspace_item();
					}
					return;
				}
			} catch (e) {
				console.log("Sidebar fix setup-patch error:", e);
			}
			return original_setup(workspace_title);
		};

		sb._sidebar_fix_patched = true;
		sb._sidebar_fix_original_setup = original_setup;
		return true;
	}

	function try_patch_workspace_switch(n) {
		if (n <= 0) return;
		if (!patch_workspace_switch()) {
			setTimeout(function () { try_patch_workspace_switch(n - 1); }, 300);
		}
	}

	// ── Pick the right workspace on (hard) refresh ─────────────────────

	function find_candidate_workspaces(entity) {
		var map = frappe.boot.workspace_sidebar_item || {};
		var out = [];
		Object.keys(map).forEach(function (key) {
			var data = map[key];
			if (!data || !data.items) return;
			var matched = false;
			for (var i = 0; i < data.items.length && !matched; i++) {
				var item = data.items[i];
				if (item && item.link_to === entity) { matched = true; break; }
				var nested = (item && item.nested_items) || [];
				for (var j = 0; j < nested.length; j++) {
					if (nested[j] && nested[j].link_to === entity) { matched = true; break; }
				}
			}
			if (matched) out.push(data.label || key);
		});
		return out;
	}

	function pick_correct_workspace() {
		try {
			var route = frappe.get_route() || [];
			if (route.length < 2) return null; // workspace URL; trust Frappe
			var entity = route[1];
			if (!entity) return null;

			var candidates = find_candidate_workspaces(entity);
			if (!candidates.length) return null;
			if (candidates.length === 1) return candidates[0];

			var last = null;
			try { last = localStorage.getItem("sidebar_fix_last_workspace"); } catch (e) {}
			if (last && candidates.indexOf(last) !== -1) return last;
			return candidates[0];
		} catch (e) {
			return null;
		}
	}

	function save_last_workspace() {
		try {
			if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.sidebar_title) {
				localStorage.setItem("sidebar_fix_last_workspace", frappe.app.sidebar.sidebar_title);
			}
		} catch (e) {}
	}

	function fix_initial_workspace() {
		if (!frappe.app || !frappe.app.sidebar) return;
		var sb = frappe.app.sidebar;
		var correct = pick_correct_workspace();
		if (!correct) return;
		if (sb.sidebar_title === correct) return;
		var setup = sb._sidebar_fix_original_setup;
		if (typeof setup !== "function") return;
		try { setup(correct); } catch (e) { console.log("Sidebar fix initial-workspace error:", e); }
	}

	function fix_initial_workspace_retry(n) {
		if (n <= 0) return;
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar._sidebar_fix_patched) {
			fix_initial_workspace();
		} else {
			setTimeout(function () { fix_initial_workspace_retry(n - 1); }, 300);
		}
	}

	// ── Init ───────────────────────────────────────────────────────────

	function init() {
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return false;
		if (_initialized) return true;
		_initialized = true;

		try_patch_workspace_switch(20);
		fix_initial_workspace_retry(20);
		$(window).on("beforeunload", save_last_workspace);

		sb.addEventListener("click", on_click, true);

		// MutationObserver: when Frappe sets active-sidebar on the wrong item,
		// override it if we have a _last_clicked target.
		var _overriding = false;
		var observer = new MutationObserver(function () {
			if (!_last_clicked || _overriding) return;
			var correct = find_dom_by_label(_last_clicked.label);
			if (!correct) return;
			var inner = correct.querySelector(".standard-sidebar-item") || correct;
			if (inner.classList.contains("active-sidebar")) return;
			_overriding = true;
			set_active(correct);
			setTimeout(function () { _overriding = false; }, 50);
		});
		observer.observe(sb, { attributes: true, attributeFilter: ["class"], subtree: true });

		var on_route = function () {
			setTimeout(function () { fix_active_retry(5); }, 300);
			setTimeout(save_last_workspace, 500);
		};
		if (frappe.router && typeof frappe.router.on === "function")
			frappe.router.on("change", on_route);
		else
			$(document).on("page-change", on_route);

		setTimeout(function () { fix_active_retry(5); }, 300);
		return true;
	}

	function try_init(n) {
		if (n <= 0) return;
		if (!init()) setTimeout(function () { try_init(n - 1); }, 500);
	}

	$(document).ready(function () { try_init(10); });
})();
```

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `<app_name>/api/boot.py` | Create or extend | Spacer + Section Break boot fixes |
| `<app_name>/public/js/sidebar_fix.js` | Create | All client-side fixes |
| `<app_name>/hooks.py` | Modify | Register boot_session + app_include_js |

## Verification Steps

After deploy (and a hard refresh — `Cmd+Shift+R` or `Ctrl+Shift+R`):

### Step 1: Verify selectors

Open browser console and run:
```javascript
document.querySelectorAll('.body-sidebar-container').length // should return 1
document.querySelector('.body-sidebar[data-title]')?.getAttribute('data-title') // should return current workspace name
```

### Step 2: Verify boot.py is running

```javascript
frappe.boot.workspace_sidebar_item.<your_workspace_lowercase>.items
    .filter(function(i) { return i.type === 'Spacer'; })
    .every(function(i) { return i.standard === true; })
// should return true (or true if no spacers)
```

### Step 3: Verify dropdown renders

Visually check the workspace sidebar. The Section Break should render with:
- An icon (if you set one)
- A label
- A collapse chevron
- Children indented below

### Step 4: Verify filter application

Click a sidebar item that has `filters` set. The list view should be filtered automatically.

### Step 5: Verify active state

For a workspace where two items link to the same DocType with different filters:
1. Click one item → it should highlight, list shows its filtered view
2. Click the other → highlight switches, list re-filters

### Step 6: Verify workspace persistence

1. From workspace A, click a sidebar link to a DocType
2. The current workspace should NOT change
3. Hard-refresh the page
4. The workspace should remain the same (not jump to a different one)

## Troubleshooting

**Symptom: JS doesn't run**
- Hard refresh to clear bundle cache
- Verify in console: `document.querySelectorAll('script[src*="sidebar_fix"]').length` should be 1
- Check the file path in `hooks.py` matches the actual path under `assets/<app_name>/js/`

**Symptom: Active state still wrong**
- Inspect the highlighted element. The class should be `.active-sidebar` on `.standard-sidebar-item`. If it's a different class, this Frappe version uses different selectors and the spec needs updating.

**Symptom: Dropdown looks wrong (bare divider, no icon)**
- Edit the Section Break row in Workspace Sidebar config → check **Indent**. If unchecked, save it checked. The `boot.py` fix handles this for new boot data, but the UI checkbox is the source of truth.

**Symptom: 404 on `/undefined` in console**
- Cosmetic Frappe core bug in `sidebar_header.js:320` (`add_app_item` reads undefined `icon_url`). Doesn't affect functionality.

## Known Limitations

- **Sidebar Item Group is broken in v16.** Don't use it. Use Section Break with a label.
- **Multiple matching workspaces on hard-refresh:** When a doctype is listed in 2+ workspaces, the localStorage hint picks the last-used one. First-time users land on the alphabetically-first workspace.
- **Polling delay for active state:** Up to 200ms × 25 attempts = 5 seconds for active state to settle. Usually resolves within 600ms.

## Removing the Fix

If Frappe addresses these bugs upstream:

1. Remove the Spacer/Section Break loop from `boot.py`
2. Remove `sidebar_fix.js` from `app_include_js` in `hooks.py`
3. Delete the `sidebar_fix.js` file
4. Workspace Sidebar config (Indent, Child Item, no Sidebar Item Group) should remain — that's standard Frappe practice anyway.

## Upstream Issues Referenced

- frappe/frappe#37872 — Section Break / Item Group rendering
- frappe/frappe#35881 — TypeLink early-return guard
- frappe/frappe#37981 — Active state matching
- frappe/frappe#36317 — Workspace switching during navigation
