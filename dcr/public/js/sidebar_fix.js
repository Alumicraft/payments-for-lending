/**
 * DCR Sidebar Fix — Frappe v16
 *
 * 1. Applies sidebar item filters as frappe.route_options on click
 * 2. Corrects active-state highlighting for duplicate-doctype items
 */
(function () {
	"use strict";

	var _initialized = false;
	var _last_clicked = null;

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
		// Frappe uses .active-sidebar on .standard-sidebar-item (not .active on container)
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

	// -- Click handler (capture phase) --

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

		// Apply filters as route_options
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

		// Track click for active state — MutationObserver will enforce it
		_last_clicked = { label: label, link_to: item.link_to };
		// Clear after 5 seconds so observer stops overriding
		setTimeout(function () { _last_clicked = null; }, 5000);
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

	// -- Init --

	function init() {
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return false;
		if (_initialized) return true;
		_initialized = true;

		sb.addEventListener("click", on_click, true);

		// MutationObserver: when Frappe sets .active on the wrong item,
		// override it if we have a _last_clicked target
		var _overriding = false;
		var observer = new MutationObserver(function () {
			if (!_last_clicked || _overriding) return;
			var correct = find_dom_by_label(_last_clicked.label);
			if (!correct) return;
			var correctInner = correct.querySelector(".standard-sidebar-item") || correct;
			if (correctInner.classList.contains("active-sidebar")) return;
			_overriding = true;
			set_active(correct);
			setTimeout(function () { _overriding = false; }, 50);
		});
		observer.observe(sb, { attributes: true, attributeFilter: ["class"], subtree: true });

		var on_route = function () {
			setTimeout(function () { fix_active_retry(5); }, 300);
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
