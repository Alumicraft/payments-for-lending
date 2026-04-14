/**
 * DCR Sidebar Fix
 *
 * Fixes three Frappe v16 sidebar bugs:
 *
 * 1. Sidebar items with `filters` don't apply those filters when
 *    clicked — Frappe only applies `route_options`, not `filters`.
 *    We intercept clicks and set frappe.route_options from the
 *    item's filters before Frappe navigates.
 *
 * 2. Active state highlights the wrong item when multiple sidebar
 *    items link to the same DocType with different filters.
 *    We compare the list view's current filters against each sidebar
 *    item's filters and set the correct one as active.
 *
 * 3. Sidebar Item Group items try to navigate (causing 404 errors).
 *    We block the click from propagating.
 *
 * Safe to remove if Frappe addresses these upstream.
 */
(function () {
	"use strict";

	// -- Helpers --

	function parse_filters(str) {
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
		if (el) return el.getAttribute("data-workspace");
		return null;
	}

	function find_sidebar_item_by_label(label) {
		var ws_name = get_workspace_name();
		if (!ws_name) return null;
		var ws = (frappe.boot.workspace_sidebar_item || {})[ws_name];
		if (!ws || !ws.items) return null;

		for (var i = 0; i < ws.items.length; i++) {
			if (ws.items[i].label === label) return ws.items[i];
		}
		return null;
	}

	function get_label_from_container(container) {
		var el = container.querySelector(".sidebar-item-label");
		if (el) return el.textContent.trim();
		var anchor = container.querySelector("a, .standard-sidebar-item");
		if (anchor) return anchor.textContent.trim();
		return null;
	}

	function set_active(container) {
		var sidebar_el = document.querySelector(".workspace-sidebar");
		if (!sidebar_el) return;
		var all = sidebar_el.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < all.length; i++) {
			all[i].classList.remove("active");
		}
		container.classList.add("active");
	}

	// -- Click handler: apply filters + fix active state --

	function on_sidebar_click(e) {
		var container = e.target.closest(".sidebar-item-container");
		if (!container) return;

		var label = get_label_from_container(container);
		if (!label) return;

		var item = find_sidebar_item_by_label(label);
		if (!item) return;

		// Block Sidebar Item Group clicks — they're group headers, not links
		if (item.type === "Sidebar Item Group") {
			e.preventDefault();
			e.stopPropagation();
			return;
		}

		// Apply filters as route_options before Frappe navigates
		if (item.type === "Link" && item.filters) {
			var filters = parse_filters(item.filters);
			if (filters.length > 0) {
				var route_opts = {};
				for (var i = 0; i < filters.length; i++) {
					var f = filters[i];
					// f = [doctype, field, operator, value]
					if (f[2] === "=") {
						route_opts[f[1]] = f[3];
					} else {
						route_opts[f[1]] = [f[2], f[3]];
					}
				}
				frappe.route_options = route_opts;
			}
		}

		// Fix active state after navigation completes
		setTimeout(function () {
			set_active(container);
		}, 300);
	}

	// -- Route change handler: fix active state on page load/navigation --

	function fix_active_on_route_change() {
		if (typeof cur_list === "undefined" || !cur_list || !cur_list.doctype) return;

		var current_doctype = cur_list.doctype;
		var ws_name = get_workspace_name();
		if (!ws_name) return;

		var ws = (frappe.boot.workspace_sidebar_item || {})[ws_name];
		if (!ws || !ws.items) return;

		// Find all Link items pointing to this doctype
		var matches = [];
		for (var i = 0; i < ws.items.length; i++) {
			var item = ws.items[i];
			if (item.type === "Link" && item.link_to === current_doctype) {
				matches.push(item);
			}
		}
		if (matches.length <= 1) return;

		// Get current list view filters
		var current_filters = [];
		try {
			current_filters = cur_list.filter_area.get();
		} catch (e) { return; }

		// Score each sidebar item by filter match
		var best_match = null;
		var best_score = -1;

		for (var i = 0; i < matches.length; i++) {
			var item = matches[i];
			var item_filters = parse_filters(item.filters);

			// No filters on item: matches when list has no filters
			if (item_filters.length === 0) {
				if (current_filters.length === 0 && 0 > best_score) {
					best_score = 0;
					best_match = item;
				}
				continue;
			}

			// Check if all item filters are in current list filters
			var score = 0;
			var all_match = true;
			for (var j = 0; j < item_filters.length; j++) {
				var f = item_filters[j];
				var found = false;
				for (var k = 0; k < current_filters.length; k++) {
					var cf = current_filters[k];
					if (cf[0] === f[0] && cf[1] === f[1] &&
						cf[2] === f[2] && String(cf[3]) === String(f[3])) {
						found = true;
						break;
					}
				}
				if (found) {
					score++;
				} else {
					all_match = false;
					break;
				}
			}

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
		for (var i = 0; i < items_els.length; i++) {
			var label = get_label_from_container(items_els[i]);
			if (label === best_match.label) {
				set_active(items_els[i]);
				return;
			}
		}
	}

	function fix_active_with_retry(retries) {
		if (retries <= 0) return;
		if (typeof cur_list !== "undefined" && cur_list && cur_list.filter_area) {
			fix_active_on_route_change();
		} else {
			setTimeout(function () {
				fix_active_with_retry(retries - 1);
			}, 200);
		}
	}

	// -- Initialize --

	function init() {
		// Attach click handler on capture phase so it fires before Frappe's handler
		var sidebar_el = document.querySelector(".workspace-sidebar");
		if (sidebar_el) {
			sidebar_el.addEventListener("click", on_sidebar_click, true);
		}

		// Fix active state on route changes
		var on_change = function () {
			setTimeout(function () {
				fix_active_with_retry(5);
			}, 300);
		};

		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", on_change);
		} else {
			$(document).on("page-change", on_change);
		}

		// Initial fix
		setTimeout(function () {
			fix_active_with_retry(5);
		}, 500);
	}

	$(document).ready(function () {
		// Small delay to let sidebar render first
		setTimeout(init, 300);
	});
})();
