/**
 * DCR Sidebar Fix
 *
 * Fixes Frappe v16 sidebar bugs:
 * 1. Applies sidebar item `filters` as route_options on click
 *    (Frappe ignores the filters field during navigation)
 * 2. Corrects active-state highlighting for duplicate-doctype items
 * 3. Makes Sidebar Item Group items collapsible group headers
 *
 * Safe to remove if Frappe addresses these upstream.
 */
(function () {
	"use strict";

	var _initialized = false;
	var _last_clicked = null; // {label, link_to} — tracks sidebar clicks
	var _groups = {};         // group label → {child_els, collapsed, chevron, state_key}

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

	function get_sidebar_items() {
		var ws_name = get_workspace_name();
		if (!ws_name) return [];
		var ws = (frappe.boot.workspace_sidebar_item || {})[ws_name];
		return (ws && ws.items) ? ws.items : [];
	}

	function get_label_from_container(container) {
		var el = container.querySelector(".sidebar-item-label");
		if (el) return el.textContent.trim();
		var anchor = container.querySelector("a, .standard-sidebar-item");
		if (anchor) return anchor.textContent.trim();
		return null;
	}

	function find_container_by_label(sidebar_el, label) {
		var containers = sidebar_el.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < containers.length; i++) {
			if (get_label_from_container(containers[i]) === label) return containers[i];
		}
		return null;
	}

	function set_active(sidebar_el, container) {
		var all = sidebar_el.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < all.length; i++) {
			all[i].classList.remove("active");
		}
		container.classList.add("active");
	}

	// -- Collapsible groups --

	function setup_collapsible_groups(sidebar_el) {
		var items = get_sidebar_items();
		if (!items.length) return;

		for (var i = 0; i < items.length; i++) {
			if (items[i].type !== "Sidebar Item Group") continue;

			var group = items[i];
			var children = [];

			for (var j = i + 1; j < items.length; j++) {
				if (items[j]._dcr_child) {
					children.push(items[j]);
				} else {
					break;
				}
			}
			if (children.length === 0) continue;

			var group_el = find_container_by_label(sidebar_el, group.label);
			if (!group_el) continue;

			var child_els = [];
			for (var k = 0; k < children.length; k++) {
				var cel = find_container_by_label(sidebar_el, children[k].label);
				if (cel) child_els.push(cel);
			}
			if (child_els.length === 0) continue;

			// State
			var state_key = "dcr_group_" + group.label;
			var collapsed = localStorage.getItem(state_key) === "true";

			// Add chevron
			var anchor = group_el.querySelector(".standard-sidebar-item") ||
			             group_el.querySelector("a");
			var chevron = null;
			if (anchor) {
				anchor.style.display = "flex";
				anchor.style.alignItems = "center";
				anchor.style.cursor = "pointer";

				chevron = document.createElement("svg");
				chevron.setAttribute("width", "12");
				chevron.setAttribute("height", "12");
				chevron.setAttribute("viewBox", "0 0 24 24");
				chevron.style.marginLeft = "auto";
				chevron.style.flexShrink = "0";
				chevron.style.transition = "transform 0.2s";
				chevron.innerHTML = '<path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>';
				anchor.appendChild(chevron);
			}

			// Indent children
			for (var m = 0; m < child_els.length; m++) {
				child_els[m].style.paddingLeft = "15px";
			}

			// Apply initial collapsed state
			if (collapsed) {
				for (var m = 0; m < child_els.length; m++) {
					child_els[m].style.display = "none";
				}
				if (chevron) chevron.style.transform = "rotate(-90deg)";
			}

			_groups[group.label] = {
				child_els: child_els,
				collapsed: collapsed,
				chevron: chevron,
				state_key: state_key,
			};
		}
	}

	function toggle_group(label) {
		var g = _groups[label];
		if (!g) return;
		g.collapsed = !g.collapsed;
		localStorage.setItem(g.state_key, g.collapsed ? "true" : "false");
		for (var i = 0; i < g.child_els.length; i++) {
			g.child_els[i].style.display = g.collapsed ? "none" : "";
		}
		if (g.chevron) {
			g.chevron.style.transform = g.collapsed ? "rotate(-90deg)" : "";
		}
	}

	// -- Click handler --

	function on_sidebar_click(e) {
		var container = e.target.closest(".sidebar-item-container");
		if (!container) return;

		var sidebar_el = document.querySelector(".body-sidebar-container");
		if (!sidebar_el) return;

		var label = get_label_from_container(container);
		if (!label) return;

		// Find matching boot data item
		var items = get_sidebar_items();
		var item = null;
		for (var i = 0; i < items.length; i++) {
			if (items[i].label === label) { item = items[i]; break; }
		}
		if (!item) return;

		// Sidebar Item Group → toggle collapse, block navigation
		if (item.type === "Sidebar Item Group") {
			e.preventDefault();
			e.stopPropagation();
			toggle_group(label);
			return;
		}

		// Link items → apply filters and track click
		if (item.type === "Link") {
			// Apply filters as route_options
			if (item.filters) {
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

			// Track this click for active-state priority
			_last_clicked = { label: label, link_to: item.link_to };

			// Set active after navigation
			setTimeout(function () {
				set_active(sidebar_el, container);
			}, 400);
		}
	}

	// -- Active state on route change --

	function fix_active_state() {
		var sidebar_el = document.querySelector(".body-sidebar-container");
		if (!sidebar_el) return;

		// If a sidebar item was just clicked, honor it
		if (_last_clicked) {
			var current_doctype = null;
			if (typeof cur_list !== "undefined" && cur_list) {
				current_doctype = cur_list.doctype;
			}
			// Only honor click if we're still on the same doctype
			if (current_doctype && current_doctype === _last_clicked.link_to) {
				var target = find_container_by_label(sidebar_el, _last_clicked.label);
				if (target) {
					set_active(sidebar_el, target);
					return;
				}
			}
			_last_clicked = null;
		}

		// Fallback: match by comparing list filters against sidebar item filters
		if (typeof cur_list === "undefined" || !cur_list || !cur_list.doctype) return;

		var current_doctype = cur_list.doctype;
		var items = get_sidebar_items();
		var matches = [];
		for (var i = 0; i < items.length; i++) {
			if (items[i].type === "Link" && items[i].link_to === current_doctype) {
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

		// Click handler (capture phase — fires before Frappe)
		sidebar_el.addEventListener("click", on_sidebar_click, true);

		// Collapsible groups
		setup_collapsible_groups(sidebar_el);

		// Route change handler
		var on_change = function () {
			setTimeout(function () { fix_active_with_retry(5); }, 300);
		};

		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", on_change);
		} else {
			$(document).on("page-change", on_change);
		}

		// Initial active state fix
		setTimeout(function () { fix_active_with_retry(5); }, 300);

		return true;
	}

	function try_init(retries) {
		if (retries <= 0) return;
		if (!init()) {
			setTimeout(function () { try_init(retries - 1); }, 500);
		}
	}

	// Start: retry init up to 10 times (5 seconds total)
	$(document).ready(function () {
		try_init(10);
	});
})();
