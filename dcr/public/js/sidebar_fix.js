/**
 * DCR Sidebar Fix
 *
 * Fixes Frappe v16 sidebar bugs:
 *
 * 1. Sidebar items with `filters` don't apply those filters when
 *    clicked — Frappe only applies `route_options`, not `filters`.
 *    We intercept clicks and set frappe.route_options from the
 *    item's filters before Frappe navigates.
 *
 * 2. Active state highlights the wrong item when multiple sidebar
 *    items link to the same DocType with different filters.
 *
 * 3. Sidebar Item Group items try to navigate (causing 404 errors).
 *    We make them collapsible group headers instead.
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

	function get_sidebar_items() {
		var ws_name = get_workspace_name();
		if (!ws_name) return [];
		var ws = (frappe.boot.workspace_sidebar_item || {})[ws_name];
		return (ws && ws.items) ? ws.items : [];
	}

	function find_item_by_label(label) {
		var items = get_sidebar_items();
		for (var i = 0; i < items.length; i++) {
			if (items[i].label === label) return items[i];
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

	function find_container_by_label(label) {
		var sidebar_el = document.querySelector(".workspace-sidebar");
		if (!sidebar_el) return null;
		var containers = sidebar_el.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < containers.length; i++) {
			if (get_label_from_container(containers[i]) === label) return containers[i];
		}
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

	// -- Collapsible groups --

	// Map of group label → { child_els, collapsed, chevron }
	var _groups = {};

	function setup_collapsible_groups() {
		var items = get_sidebar_items();
		if (!items.length) return;

		for (var i = 0; i < items.length; i++) {
			if (items[i].type !== "Sidebar Item Group") continue;

			var group = items[i];
			var children = [];

			// Collect subsequent child items (child flag set)
			for (var j = i + 1; j < items.length; j++) {
				if (items[j].child || items[j].child_item) {
					children.push(items[j]);
				} else {
					break;
				}
			}

			if (children.length === 0) continue;

			var group_el = find_container_by_label(group.label);
			if (!group_el) continue;

			var child_els = [];
			for (var k = 0; k < children.length; k++) {
				var cel = find_container_by_label(children[k].label);
				if (cel) child_els.push(cel);
			}

			if (child_els.length === 0) continue;

			// Build the collapsible UI
			var state_key = "dcr_sidebar_group_" + group.label;
			var collapsed = localStorage.getItem(state_key) === "true";

			// Add chevron to group item
			var anchor = group_el.querySelector(".standard-sidebar-item") ||
			             group_el.querySelector("a");
			var chevron = null;

			if (anchor) {
				// Add flex layout for label + chevron
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

			// Indent child items
			for (var m = 0; m < child_els.length; m++) {
				child_els[m].style.paddingLeft = "15px";
			}

			// Apply initial state
			if (collapsed) {
				for (var m = 0; m < child_els.length; m++) {
					child_els[m].style.display = "none";
				}
				if (chevron) chevron.style.transform = "rotate(-90deg)";
			}

			// Store for toggle handler
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

	// -- Click handler: apply filters + fix active state + toggle groups --

	function on_sidebar_click(e) {
		var container = e.target.closest(".sidebar-item-container");
		if (!container) return;

		var label = get_label_from_container(container);
		if (!label) return;

		var item = find_item_by_label(label);
		if (!item) return;

		// Sidebar Item Group: toggle collapse, block navigation
		if (item.type === "Sidebar Item Group") {
			e.preventDefault();
			e.stopPropagation();
			toggle_group(label);
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

	// -- Route change handler: fix active state --

	function fix_active_on_route_change() {
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
		try {
			current_filters = cur_list.filter_area.get();
		} catch (e) { return; }

		var best_match = null;
		var best_score = -1;

		for (var i = 0; i < matches.length; i++) {
			var item = matches[i];
			var item_filters = parse_filters(item.filters);

			if (item_filters.length === 0) {
				if (current_filters.length === 0 && 0 > best_score) {
					best_score = 0;
					best_match = item;
				}
				continue;
			}

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
				if (found) { score++; } else { all_match = false; break; }
			}

			if (all_match && score > best_score) {
				best_score = score;
				best_match = item;
			}
		}

		if (!best_match) return;

		var target = find_container_by_label(best_match.label);
		if (target) set_active(target);
	}

	function fix_active_with_retry(retries) {
		if (retries <= 0) return;
		if (typeof cur_list !== "undefined" && cur_list && cur_list.filter_area) {
			fix_active_on_route_change();
		} else {
			setTimeout(function () { fix_active_with_retry(retries - 1); }, 200);
		}
	}

	// -- Initialize --

	function init() {
		var sidebar_el = document.querySelector(".workspace-sidebar");
		if (!sidebar_el) return;

		// Click handler on capture phase (fires before Frappe's handlers)
		sidebar_el.addEventListener("click", on_sidebar_click, true);

		// Set up collapsible groups
		setup_collapsible_groups();

		// Fix active state on route changes
		var on_change = function () {
			setTimeout(function () { fix_active_with_retry(5); }, 300);
		};

		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", on_change);
		} else {
			$(document).on("page-change", on_change);
		}

		// Initial active state fix
		setTimeout(function () { fix_active_with_retry(5); }, 500);
	}

	$(document).ready(function () {
		setTimeout(init, 300);
	});
})();
