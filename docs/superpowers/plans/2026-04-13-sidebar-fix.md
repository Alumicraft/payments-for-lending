# Frappe v16 Workspace Sidebar Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three Frappe v16 workspace sidebar rendering bugs — missing Section Breaks, missing Sidebar Item Group labels, and wrong active-state highlighting.

**Architecture:** Fix bugs 1 (Section Break) and 2 (Item Group labels) at the data layer in `boot_session` by restructuring the flat item list into proper nested structure and marking Item Groups as `standard`. Fix bug 3 (active state) with a new client-side JS file that matches URL params against sidebar item `route_options`.

**Tech Stack:** Python (Frappe boot hook), vanilla JS (app_include_js)

**Spec:** `docs/superpowers/specs/2026-04-13-sidebar-fix-design.md`

**Note:** This project runs on Frappe Cloud with no local bench. No unit test runner is available. Each task ends with manual browser verification steps.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `dcr/api/boot.py` | Modify | Add `_nest_sidebar_items()` — restructures flat sidebar data and marks Item Groups |
| `dcr/public/js/sidebar_fix.js` | Create | Active-state matching on route changes |
| `dcr/hooks.py` | Modify | Add `sidebar_fix.js` to `app_include_js` |

---

### Task 1: Boot Data Restructure

**Files:**
- Modify: `dcr/api/boot.py`

- [ ] **Step 1: Add `_nest_sidebar_items` function**

Add this function after the existing `boot_session` function in `dcr/api/boot.py`:

```python
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
			# Mark Sidebar Item Group items as standard so TypeLink.make()
			# doesn't skip them (the guard exempts standard items).
			# Side effect: hides drag/settings controls in sidebar edit mode.
			if item.get("type") == "Sidebar Item Group":
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
```

- [ ] **Step 2: Call `_nest_sidebar_items` from `boot_session`**

Add the call at the end of the existing `boot_session` function. The full function should now be:

```python
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
	_nest_sidebar_items(bootinfo)
```

- [ ] **Step 3: Commit**

```bash
git add dcr/api/boot.py
git commit -m "fix: nest sidebar items under Section Breaks for v16 renderer

Frappe v16's TypeSectionBreak.make() returns early when nested_items is
empty. The boot data stores items flat, so sections never render.
Restructure the flat list to populate nested_items on Section Breaks.

Also marks Sidebar Item Group items as standard=True to bypass the
TypeLink.make() early-return guard that hides their labels.

Refs: frappe/frappe#37872, frappe/frappe#35881"
```

- [ ] **Step 4: Deploy and verify Section Breaks + Item Groups**

Push to GitHub and deploy via Frappe Cloud. After deploy:

1. Navigate to the Contacts workspace
2. Verify a visual separator/divider appears between "Home" and "Dealers"
3. Verify a visual separator appears between "Factories" and the "Masters" group
4. Verify "Masters" text label appears next to the collapse chevron
5. Verify "All Customers" and "All Suppliers" appear nested under Masters
6. Click the Masters collapse chevron — child items should hide/show
7. Navigate to Home workspace — verify desktop icons still render correctly
8. Check browser console for errors

---

### Task 2: Active-State Fix

**Files:**
- Create: `dcr/public/js/sidebar_fix.js`

- [ ] **Step 1: Create `sidebar_fix.js`**

Create `dcr/public/js/sidebar_fix.js`:

```javascript
/**
 * DCR Sidebar Active-State Fix
 *
 * When multiple sidebar items link to the same DocType with different
 * route_options (e.g., "Suppliers" and "Factories" both → Supplier),
 * Frappe highlights the first match by doctype, ignoring URL params.
 *
 * This fix runs after each route change, compares URL params against
 * each sidebar item's route_options from boot data, and sets the
 * correct item as active.
 *
 * Safe to remove if Frappe addresses this upstream.
 */
(function () {
	"use strict";

	// -- Helpers --

	function parse_json_safe(str) {
		if (!str) return {};
		try {
			return JSON.parse(str);
		} catch (e) {
			return {};
		}
	}

	function get_url_params() {
		var params = {};
		var search = window.location.search;
		if (!search) return params;
		var sp = new URLSearchParams(search);
		sp.forEach(function (value, key) {
			try {
				params[key] = decodeURIComponent(value);
			} catch (e) {
				params[key] = value;
			}
		});
		return params;
	}

	function get_workspace_name() {
		// Priority 1: Frappe sidebar state
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.current_workspace) {
			return frappe.app.sidebar.current_workspace;
		}
		// Priority 2: DOM data attribute
		var el = document.querySelector("[data-workspace]");
		if (el) {
			return el.getAttribute("data-workspace");
		}
		// Priority 3: Match current doctype against all workspace items
		var route = frappe.get_route();
		if (!route || !route.length) return null;
		var doctype_slug = route[0];
		var boot_data = frappe.boot.workspace_sidebar_item || {};
		for (var ws_name in boot_data) {
			if (!boot_data.hasOwnProperty(ws_name)) continue;
			if (items_contain_slug(boot_data[ws_name].items || [], doctype_slug)) {
				return ws_name;
			}
		}
		return null;
	}

	function items_contain_slug(items, slug) {
		for (var i = 0; i < items.length; i++) {
			var item = items[i];
			if (item.link_to && frappe.router.slug(item.link_to) === slug) {
				return true;
			}
			var nested = item.nested_items || [];
			for (var j = 0; j < nested.length; j++) {
				if (nested[j].link_to && frappe.router.slug(nested[j].link_to) === slug) {
					return true;
				}
			}
		}
		return false;
	}

	function flatten_link_items(items) {
		var flat = [];
		for (var i = 0; i < items.length; i++) {
			if (items[i].type === "Link") {
				flat.push(items[i]);
			}
			var nested = items[i].nested_items || [];
			for (var j = 0; j < nested.length; j++) {
				if (nested[j].type === "Link") {
					flat.push(nested[j]);
				}
			}
		}
		return flat;
	}

	// -- Main fix --

	function fix_active_state() {
		var route = frappe.get_route();
		if (!route || !route.length) return;

		var doctype_slug = route[0];
		var url_params = get_url_params();

		// Only intervene when URL has query params
		if (!Object.keys(url_params).length) return;

		// Resolve workspace — exit silently if unresolved
		var ws_name = get_workspace_name();
		if (!ws_name) return;

		var boot_data = frappe.boot.workspace_sidebar_item || {};
		var ws = boot_data[ws_name];
		if (!ws || !ws.items) return;

		// Find all Link items matching current doctype
		var all_items = flatten_link_items(ws.items);
		var matches = [];
		for (var i = 0; i < all_items.length; i++) {
			if (all_items[i].link_to && frappe.router.slug(all_items[i].link_to) === doctype_slug) {
				matches.push(all_items[i]);
			}
		}

		// Only intervene for duplicate doctype links
		if (matches.length <= 1) return;

		// Score each match by route_options/filters overlap with URL params
		var best_match = null;
		var best_score = -1;

		for (var i = 0; i < matches.length; i++) {
			var item = matches[i];
			var opts = parse_json_safe(item.route_options);
			var filters = parse_json_safe(item.filters);
			var item_params = {};

			// Merge filters and route_options
			var key;
			for (key in filters) {
				if (filters.hasOwnProperty(key)) item_params[key] = String(filters[key]);
			}
			for (key in opts) {
				if (opts.hasOwnProperty(key)) item_params[key] = String(opts[key]);
			}

			var score = 0;
			var all_match = true;

			for (key in item_params) {
				if (!item_params.hasOwnProperty(key)) continue;
				var decoded;
				try {
					decoded = decodeURIComponent(item_params[key]);
				} catch (e) {
					decoded = item_params[key];
				}
				if (url_params[key] === decoded) {
					score++;
				} else {
					all_match = false;
				}
			}

			// All item params must match URL; highest score wins.
			// Tie-breaker: first in document order (lower array index).
			if (all_match && score > best_score) {
				best_score = score;
				best_match = item;
			}
		}

		if (!best_match) return;

		// Find DOM element by label and set active
		var sidebar_el = document.querySelector(".workspace-sidebar");
		if (!sidebar_el) return;

		var items_els = sidebar_el.querySelectorAll(".sidebar-item-container");
		var target = null;

		for (var i = 0; i < items_els.length; i++) {
			var label_el = items_els[i].querySelector(".sidebar-item-label");
			if (!label_el) continue;
			var text = (label_el.textContent || "").trim();
			if (text === best_match.label) {
				target = items_els[i];
				break;
			}
		}

		if (!target) return;

		// Remove active from all, set on target
		for (var i = 0; i < items_els.length; i++) {
			items_els[i].classList.remove("active");
		}
		target.classList.add("active");
	}

	// -- Hook into route changes --

	function attach() {
		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", function () {
				setTimeout(fix_active_state, 300);
			});
		} else {
			$(document).on("page-change", function () {
				setTimeout(fix_active_state, 300);
			});
		}
	}

	$(document).ready(function () {
		attach();
		setTimeout(fix_active_state, 500);
	});
})();
```

- [ ] **Step 2: Commit**

```bash
git add dcr/public/js/sidebar_fix.js
git commit -m "feat: add active-state fix for duplicate-doctype sidebar items

When multiple sidebar items link to the same DocType with different
route_options (e.g., Suppliers and Factories both link to Supplier),
Frappe highlights the first match by doctype name. This fix compares
URL params against each item's route_options from boot data and sets
the correct item as active."
```

---

### Task 3: Integration and Verification

**Files:**
- Modify: `dcr/hooks.py`

- [ ] **Step 1: Update `app_include_js` in hooks.py**

Change line 10 from:

```python
app_include_js = "/assets/dcr/js/icon_fix.js"
```

to:

```python
app_include_js = ["/assets/dcr/js/icon_fix.js", "/assets/dcr/js/sidebar_fix.js"]
```

- [ ] **Step 2: Commit**

```bash
git add dcr/hooks.py
git commit -m "chore: add sidebar_fix.js to app_include_js"
```

- [ ] **Step 3: Deploy and run full verification**

Push to GitHub and deploy via Frappe Cloud. After deploy, verify all fixes:

**Section Breaks (Bug 1):**
1. Open the Contacts workspace
2. Confirm a visual divider/separator appears between "Home" and the "Dealers/Suppliers/Factories" group
3. Confirm a divider appears between "Factories" and the "Masters" section

**Item Group Labels (Bug 2):**
4. Confirm "Masters" text label appears next to its collapse chevron
5. Click the chevron — "All Customers" and "All Suppliers" should collapse/expand
6. Confirm child items appear visually indented under Masters

**Active State (Bug 3):**
7. Click "Suppliers" in the sidebar — it should highlight, URL should be `/app/supplier` (or with its route_options)
8. Click "Factories" — it should highlight instead of "Suppliers", URL should include the Factories route_options params
9. Click "Suppliers" again — highlight should switch back

**No Regressions:**
10. Navigate to Home — desktop icons should render with images (not letter squares)
11. Open browser console — no new JS errors
12. Check other workspace sidebars (if any) — items should still render normally

- [ ] **Step 4: Adjust DOM selectors if needed**

The active-state fix uses `.sidebar-item-container` and `.sidebar-item-label` selectors based on Frappe v16 source analysis. If active state isn't toggling correctly after deploy:

1. Open browser DevTools on the sidebar
2. Inspect a sidebar item's DOM structure
3. Identify the correct container class (the element that gets `.active`)
4. Identify the correct label element (contains the item text)
5. Update selectors in `sidebar_fix.js` and redeploy

---

## Rollback

If something breaks:
- **Quick:** Remove `"/assets/dcr/js/sidebar_fix.js"` from `app_include_js` in hooks.py and remove the `_nest_sidebar_items(bootinfo)` call from boot.py. Redeploy.
- **Full:** Revert all three commits.
