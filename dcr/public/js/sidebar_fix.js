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
