/**
 * DCR Sidebar Fix
 *
 * 1. Applies sidebar item `filters` as route_options on click
 *    (Frappe ignores the filters field during navigation)
 * 2. Blocks Sidebar Item Group clicks from navigating (prevents 404)
 * 3. Corrects active-state highlighting for duplicate-doctype items
 */
(function () {
	"use strict";

	var _initialized = false;
	var _last_clicked = null;

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
		var el = document.querySelector(".body-sidebar[data-title]");
		if (el) return el.getAttribute("data-title").toLowerCase();
		return null;
	}

	function get_sidebar_items() {
		var ws_name = get_workspace_name();
		if (!ws_name) return [];
		var ws = (frappe.boot.workspace_sidebar_item || {})[ws_name];
		if (!ws || !ws.items) return [];
		// Flatten: include top-level + nested items
		var all = [];
		for (var i = 0; i < ws.items.length; i++) {
			all.push(ws.items[i]);
			var nested = ws.items[i].nested_items || [];
			for (var j = 0; j < nested.length; j++) {
				all.push(nested[j]);
			}
		}
		return all;
	}

	function get_label_from_container(container) {
		var el = container.querySelector(".sidebar-item-label");
		if (el) return el.textContent.trim();
		return null;
	}

	function set_active(sidebar_el, container) {
		var all = sidebar_el.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < all.length; i++) {
			all[i].classList.remove("active");
		}
		container.classList.add("active");
	}

	function find_container_by_label(sidebar_el, label) {
		var containers = sidebar_el.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < containers.length; i++) {
			if (get_label_from_container(containers[i]) === label) return containers[i];
		}
		return null;
	}

	// -- Click handler --

	function on_sidebar_click(e) {
		var container = e.target.closest(".sidebar-item-container");
		if (!container) return;

		var sidebar_el = document.querySelector(".body-sidebar-container");
		if (!sidebar_el) return;

		var label = get_label_from_container(container);
		if (!label) return;

		var items = get_sidebar_items();
		var item = null;
		for (var i = 0; i < items.length; i++) {
			if (items[i].label === label) { item = items[i]; break; }
		}
		if (!item) return;

		// Block Sidebar Item Group navigation (404 error)
		if (item.type === "Sidebar Item Group") {
			e.preventDefault();
			e.stopPropagation();
			return;
		}

		// Apply filters as route_options
		if (item.type === "Link" && item.filters) {
			var filters = parse_filters(item.filters);
			if (filters.length > 0) {
				var opts = {};
				for (var i = 0; i < filters.length; i++) {
					var f = filters[i];
					if (f[2] === "=") {
						opts[f[1]] = f[3];
					} else {
						opts[f[1]] = [f[2], f[3]];
					}
				}
				frappe.route_options = opts;
			}
		}

		// Track click for active state
		_last_clicked = { label: label, link_to: item.link_to };
		setTimeout(function () {
			set_active(sidebar_el, container);
		}, 400);
	}

	// -- Active state on route change --

	function fix_active_state() {
		var sidebar_el = document.querySelector(".body-sidebar-container");
		if (!sidebar_el) return;

		if (_last_clicked) {
			var current_doctype = null;
			if (typeof cur_list !== "undefined" && cur_list) {
				current_doctype = cur_list.doctype;
			}
			if (current_doctype && current_doctype === _last_clicked.link_to) {
				var target = find_container_by_label(sidebar_el, _last_clicked.label);
				if (target) {
					set_active(sidebar_el, target);
					return;
				}
			}
			_last_clicked = null;
		}

		// Fallback: match by list filters
		if (typeof cur_list === "undefined" || !cur_list || !cur_list.doctype) return;

		var items = get_sidebar_items();
		var matches = [];
		for (var i = 0; i < items.length; i++) {
			if (items[i].type === "Link" && items[i].link_to === cur_list.doctype) {
				matches.push(items[i]);
			}
		}
		if (matches.length <= 1) return;

		var current_filters = [];
		try { current_filters = cur_list.filter_area.get(); } catch (e) { return; }

		var best_match = null;
		var best_score = -1;

		for (var i = 0; i < matches.length; i++) {
			var item_filters = parse_filters(matches[i].filters);
			if (item_filters.length === 0 && current_filters.length === 0) {
				if (0 > best_score) { best_score = 0; best_match = matches[i]; }
				continue;
			}
			if (item_filters.length === 0) continue;

			var score = 0;
			var all_match = true;
			for (var j = 0; j < item_filters.length; j++) {
				var f = item_filters[j];
				var found = false;
				for (var k = 0; k < current_filters.length; k++) {
					var cf = current_filters[k];
					if (cf[1] === f[1] && cf[2] === f[2] && String(cf[3]) === String(f[3])) {
						found = true; break;
					}
				}
				if (found) { score++; } else { all_match = false; break; }
			}
			if (all_match && score > best_score) {
				best_score = score;
				best_match = matches[i];
			}
		}

		if (best_match) {
			var el = find_container_by_label(sidebar_el, best_match.label);
			if (el) set_active(sidebar_el, el);
		}
	}

	function fix_active_with_retry(retries) {
		if (retries <= 0) return;
		if (typeof cur_list !== "undefined" && cur_list && cur_list.filter_area) {
			fix_active_state();
		} else {
			setTimeout(function () { fix_active_with_retry(retries - 1); }, 200);
		}
	}

	// -- Init with retry --

	function init() {
		var sidebar_el = document.querySelector(".body-sidebar-container");
		if (!sidebar_el) return false;
		if (_initialized) return true;
		_initialized = true;

		sidebar_el.addEventListener("click", on_sidebar_click, true);

		var on_change = function () {
			setTimeout(function () { fix_active_with_retry(5); }, 300);
		};

		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", on_change);
		} else {
			$(document).on("page-change", on_change);
		}

		setTimeout(function () { fix_active_with_retry(5); }, 300);
		return true;
	}

	function try_init(retries) {
		if (retries <= 0) return;
		if (!init()) {
			setTimeout(function () { try_init(retries - 1); }, 500);
		}
	}

	$(document).ready(function () {
		try_init(10);
	});
})();
