/**
 * DCR Sidebar Fix — Frappe v16
 *
 * 1. Collapsible groups: Sidebar Item Group items toggle child visibility
 * 2. Filter application: sidebar item filters → frappe.route_options
 * 3. Active state: correct highlighting for duplicate-doctype items
 *
 * DOM selectors (verified for v16):
 *   Sidebar container: .body-sidebar-container
 *   Item container:    .sidebar-item-container[item-name="..."]
 *   Item anchor:       .item-anchor
 *   Item label:        .sidebar-item-label
 *   Workspace name:    .body-sidebar[data-title]
 */
(function () {
	"use strict";

	var _initialized = false;
	var _last_clicked = null;
	var _groups = {};

	// -- Helpers --

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

	function get_sidebar_items() {
		var ws = get_workspace_name();
		if (!ws) return [];
		var data = (frappe.boot.workspace_sidebar_item || {})[ws];
		return (data && data.items) ? data.items : [];
	}

	function find_item_by_label(label) {
		var items = get_sidebar_items();
		for (var i = 0; i < items.length; i++) {
			if (items[i].label === label) return { item: items[i], index: i };
		}
		return null;
	}

	function set_active(container) {
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return;
		var all = sb.querySelectorAll(".sidebar-item-container");
		for (var i = 0; i < all.length; i++) all[i].classList.remove("active");
		container.classList.add("active");
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

	// -- Collapsible groups --

	function setup_groups() {
		var items = get_sidebar_items();
		for (var i = 0; i < items.length; i++) {
			if (items[i].type !== "Sidebar Item Group") continue;

			var group = items[i];
			var child_labels = [];
			for (var j = i + 1; j < items.length; j++) {
				if (items[j]._dcr_child) child_labels.push(items[j].label);
				else break;
			}
			if (!child_labels.length) continue;

			var group_el = find_dom_by_label(group.label);
			if (!group_el) continue;

			var child_els = [];
			for (var k = 0; k < child_labels.length; k++) {
				var cel = find_dom_by_label(child_labels[k]);
				if (cel) {
					cel.style.paddingLeft = "15px";
					child_els.push(cel);
				}
			}
			if (!child_els.length) continue;

			// Add text chevron inside the anchor
			var anchor = group_el.querySelector(".item-anchor");
			if (!anchor) continue;

			var chevron = document.createElement("span");
			chevron.textContent = "\u25BE"; // ▾
			chevron.style.cssText = "margin-left:auto;font-size:12px;opacity:0.6;transition:transform 0.2s;display:inline-block;";
			anchor.appendChild(chevron);

			// Restore collapsed state
			var key = "dcr_group_" + group.label;
			var collapsed = localStorage.getItem(key) === "true";

			if (collapsed) {
				for (var m = 0; m < child_els.length; m++) child_els[m].style.display = "none";
				chevron.style.transform = "rotate(-90deg)";
			}

			_groups[group.label] = {
				children: child_els,
				chevron: chevron,
				collapsed: collapsed,
				key: key,
			};
		}
	}

	function toggle_group(label) {
		var g = _groups[label];
		if (!g) return;
		g.collapsed = !g.collapsed;
		localStorage.setItem(g.key, g.collapsed ? "true" : "false");
		for (var i = 0; i < g.children.length; i++) {
			g.children[i].style.display = g.collapsed ? "none" : "";
		}
		g.chevron.style.transform = g.collapsed ? "rotate(-90deg)" : "";
	}

	// -- Click handler (capture phase) --

	function on_click(e) {
		var container = e.target.closest(".sidebar-item-container");
		if (!container) return;

		var lbl_el = container.querySelector(".sidebar-item-label");
		if (!lbl_el) return;
		var label = lbl_el.textContent.trim();

		var found = find_item_by_label(label);
		if (!found) return;
		var item = found.item;

		// Sidebar Item Group → toggle, block navigation
		if (item.type === "Sidebar Item Group") {
			e.preventDefault();
			e.stopPropagation();
			toggle_group(label);
			return;
		}

		// Link → apply filters
		if (item.type === "Link" && item.filters) {
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

		// Track click + set active
		if (item.type === "Link") {
			_last_clicked = { label: label, link_to: item.link_to };
			setTimeout(function () { set_active(container); }, 400);
		}
	}

	// -- Active state on route change --

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

		var items = get_sidebar_items();
		var matches = [];
		for (var i = 0; i < items.length; i++) {
			if (items[i].type === "Link" && items[i].link_to === cur_list.doctype) {
				matches.push(items[i]);
			}
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
					if (cf[1] === f[1] && cf[2] === f[2] && String(cf[3]) === String(f[3])) { found = true; break; }
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

	// -- Init --

	function init() {
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return false;
		if (_initialized) return true;
		_initialized = true;

		sb.addEventListener("click", on_click, true);
		setup_groups();

		var on_route = function () {
			setTimeout(function () { fix_active_retry(5); }, 300);
		};
		if (frappe.router && typeof frappe.router.on === "function") {
			frappe.router.on("change", on_route);
		} else {
			$(document).on("page-change", on_route);
		}
		setTimeout(function () { fix_active_retry(5); }, 300);
		return true;
	}

	function try_init(n) {
		if (n <= 0) return;
		if (!init()) setTimeout(function () { try_init(n - 1); }, 500);
	}

	$(document).ready(function () { try_init(10); });
})();
