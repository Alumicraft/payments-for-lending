/**
 * DCR Sidebar Active-State Fix
 *
 * When multiple sidebar items link to the same DocType with different
 * filters (e.g., "Suppliers" and "Factories" both → Supplier), Frappe
 * highlights the first match by doctype, ignoring filters.
 *
 * This fix runs after each route change, compares the list view's
 * current filters against each sidebar item's filters from boot data,
 * and sets the correct item as active.
 *
 * Safe to remove if Frappe addresses this upstream.
 */
(function () {
	"use strict";

	function parse_json_safe(str) {
		if (!str) return [];
		try {
			var result = JSON.parse(str);
			return Array.isArray(result) ? result : [];
		} catch (e) {
			return [];
		}
	}

	function get_workspace_name() {
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.current_workspace) {
			return frappe.app.sidebar.current_workspace;
		}
		var el = document.querySelector("[data-workspace]");
		if (el) {
			return el.getAttribute("data-workspace");
		}
		// Match current doctype against all workspace items
		var current_doctype = get_current_doctype();
		if (!current_doctype) return null;
		var boot_data = frappe.boot.workspace_sidebar_item || {};
		for (var ws_name in boot_data) {
			if (!boot_data.hasOwnProperty(ws_name)) continue;
			var items = boot_data[ws_name].items || [];
			for (var i = 0; i < items.length; i++) {
				if (items[i].link_to === current_doctype) return ws_name;
			}
		}
		return null;
	}

	function get_current_doctype() {
		// Try cur_list first (most reliable for list views)
		if (typeof cur_list !== "undefined" && cur_list && cur_list.doctype) {
			return cur_list.doctype;
		}
		// Fallback: parse route
		var route = frappe.get_route();
		if (!route || !route.length) return null;
		// v16 route: ["doctype_slug", "view", "list"] or ["doctype_slug"]
		var slug = route[0];
		if (slug && frappe.router && frappe.router.de_slug) {
			return frappe.router.de_slug(slug);
		}
		return slug;
	}

	function get_current_filters() {
		try {
			if (typeof cur_list !== "undefined" && cur_list && cur_list.filter_area) {
				return cur_list.filter_area.get();
			}
		} catch (e) {}
		return [];
	}

	function filters_match(item_filters, current_filters) {
		// Check if all of the sidebar item's filters are present in the
		// current list view's filters.
		// item_filters: [["Supplier","supplier_group","=","Factory"], ...]
		// current_filters: same format from cur_list.filter_area.get()
		if (item_filters.length === 0) return true; // no filters = matches unfiltered

		var all_match = true;
		for (var i = 0; i < item_filters.length; i++) {
			var f = item_filters[i];
			var found = false;
			for (var j = 0; j < current_filters.length; j++) {
				var cf = current_filters[j];
				if (cf[0] === f[0] && cf[1] === f[1] &&
					cf[2] === f[2] && String(cf[3]) === String(f[3])) {
					found = true;
					break;
				}
			}
			if (!found) {
				all_match = false;
				break;
			}
		}
		return all_match;
	}

	function set_active_by_label(label) {
		var sidebar_el = document.querySelector(".workspace-sidebar");
		if (!sidebar_el) return;

		var items_els = sidebar_el.querySelectorAll(".sidebar-item-container");
		var target = null;

		for (var i = 0; i < items_els.length; i++) {
			var label_el = items_els[i].querySelector(".sidebar-item-label");
			if (!label_el) {
				// Try text content of the anchor directly
				var anchor = items_els[i].querySelector("a, .standard-sidebar-item");
				if (anchor && anchor.textContent.trim() === label) {
					target = items_els[i];
					break;
				}
				continue;
			}
			if (label_el.textContent.trim() === label) {
				target = items_els[i];
				break;
			}
		}

		if (!target) return;

		for (var i = 0; i < items_els.length; i++) {
			items_els[i].classList.remove("active");
		}
		target.classList.add("active");
	}

	function fix_active_state() {
		var current_doctype = get_current_doctype();
		if (!current_doctype) return;

		var ws_name = get_workspace_name();
		if (!ws_name) return;

		var boot_data = frappe.boot.workspace_sidebar_item || {};
		var ws = boot_data[ws_name];
		if (!ws || !ws.items) return;

		// Find all Link items pointing to the same doctype
		var matches = [];
		var items = ws.items;
		for (var i = 0; i < items.length; i++) {
			if (items[i].type === "Link" && items[i].link_to === current_doctype) {
				matches.push(items[i]);
			}
		}

		// Only intervene for duplicate doctype links
		if (matches.length <= 1) return;

		var current_filters = get_current_filters();

		// Score: sidebar item whose filters best match current list filters
		var best_match = null;
		var best_score = -1;

		for (var i = 0; i < matches.length; i++) {
			var item = matches[i];
			var item_filters = parse_json_safe(item.filters);

			// Item with no filters matches unfiltered list
			if (item_filters.length === 0 && current_filters.length === 0) {
				if (0 > best_score) {
					best_score = 0;
					best_match = item;
				}
				continue;
			}

			if (filters_match(item_filters, current_filters)) {
				var score = item_filters.length;
				if (score > best_score) {
					best_score = score;
					best_match = item;
				}
			}
		}

		if (best_match) {
			set_active_by_label(best_match.label);
		}
	}

	// Retry mechanism: cur_list may not be ready immediately after route change
	function fix_active_with_retry(retries) {
		if (retries <= 0) return;
		if (typeof cur_list !== "undefined" && cur_list && cur_list.filter_area) {
			fix_active_state();
		} else {
			setTimeout(function () {
				fix_active_with_retry(retries - 1);
			}, 200);
		}
	}

	function on_route_change() {
		// Wait for list view to load, then fix active state
		setTimeout(function () {
			fix_active_with_retry(5); // retry up to 5 times (1 second total)
		}, 300);
	}

	// Hook into route changes
	if (frappe.router && typeof frappe.router.on === "function") {
		frappe.router.on("change", on_route_change);
	} else {
		$(document).on("page-change", on_route_change);
	}

	$(document).ready(function () {
		setTimeout(function () {
			fix_active_with_retry(5);
		}, 500);
	});
})();
