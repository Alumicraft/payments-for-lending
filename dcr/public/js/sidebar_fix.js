/**
 * DCR Sidebar Fix — Frappe v16
 *
 * 1. Applies sidebar item filters as frappe.route_options on click
 * 2. Corrects active-state highlighting for duplicate-doctype items
 * 3. Prevents unwanted workspace switching when navigating to a DocType
 *    that lives in a different module's workspace. Upstream issue:
 *    frappe/frappe#36317. Frappe's set_workspace_sidebar compares URL
 *    slugs against sidebar item link_to values (title case), so the
 *    "keep current sidebar" short-circuit never fires and it falls
 *    through to module-based workspace resolution.
 */
(function () {
	"use strict";

	var _initialized = false;
	var _last_clicked = null;
	var ENTITY_WORKSPACE_PREFIX = "dcr_workspace_for_";
	var DEFAULT_WORKSPACE_BY_ENTITY = {
		"homebuildrequest": "Deals"
	};

	function parse_filters(str) {
		if (!str) return [];
		try { var r = JSON.parse(str); return Array.isArray(r) ? r : []; }
		catch (e) { return []; }
	}

	function normalize(s) {
		// Compare entities/labels regardless of slug vs title case.
		// "Home Build Request" and "home-build-request" -> "homebuildrequest"
		return (s || "").toLowerCase().replace(/[\s_-]+/g, "");
	}

	function slugify(s) {
		return (s || "")
			.toLowerCase()
			.replace(/[\s_]+/g, "-")
			.replace(/[^a-z0-9-]/g, "")
			.replace(/-+/g, "-")
			.replace(/^-|-$/g, "");
	}

	function workspace_from_slug(slug) {
		var map = frappe.boot.workspace_sidebar_item || {};
		var target = slugify(slug);
		if (!target) return null;
		if (map[slug]) return { key: slug, label: map[slug].label || slug, data: map[slug] };
		if (map[target]) return { key: target, label: map[target].label || target, data: map[target] };
		var keys = Object.keys(map);
		for (var i = 0; i < keys.length; i++) {
			var key = keys[i];
			var data = map[key] || {};
			if (slugify(key) === target || slugify(data.label) === target) {
				return { key: key, label: data.label || key, data: data };
			}
		}
		return null;
	}

	function candidate_label(label, candidates) {
		var workspace = workspace_from_slug(label);
		var target = normalize(workspace ? workspace.label : label);
		if (!target) return null;
		for (var i = 0; i < candidates.length; i++) {
			if (normalize(candidates[i]) === target) return candidates[i];
		}
		return null;
	}

	function get_workspace_for_entity(entity, candidates) {
		try {
			return candidate_label(
				localStorage.getItem(ENTITY_WORKSPACE_PREFIX + normalize(entity)),
				candidates
			);
		} catch (e) {
			return null;
		}
	}

	function default_workspace_for_entity(entity, candidates) {
		return candidate_label(DEFAULT_WORKSPACE_BY_ENTITY[normalize(entity)], candidates);
	}

	function remember_workspace_for_entity(entity, workspace_name, reason) {
		var workspace = workspace_from_slug(workspace_name);
		if (!entity || !workspace) return false;
		try {
			localStorage.setItem(ENTITY_WORKSPACE_PREFIX + normalize(entity), workspace.label);
			localStorage.setItem("dcr_last_workspace", workspace.label);
			console.info("[DCR sidebar] remembered", reason || "", entity, workspace.label);
			return true;
		} catch (e) {
			console.log("[DCR sidebar] remember error:", e);
			return false;
		}
	}

	function get_workspace_name() {
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.current_workspace) {
			return frappe.app.sidebar.current_workspace;
		}
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.sidebar_title) {
			return frappe.app.sidebar.sidebar_title;
		}
		var el = document.querySelector(".body-sidebar[data-title]");
		if (el) return el.getAttribute("data-title");
		return null;
	}

	function get_all_items() {
		var ws = get_workspace_name();
		if (!ws) return [];
		var workspace = workspace_from_slug(ws);
		var data = workspace && workspace.data;
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
		remember_workspace_for_entity(item.link_to, get_workspace_name(), "sidebar-click");

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

		// Track click — poll to enforce correct active state
		// (MutationObserver fails if Frappe rebuilds the entire sidebar DOM)
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

	// -- Prevent unwanted workspace switching --
	// Frappe's set_workspace_sidebar uses URL slugs (e.g. "home-build-request")
	// to look up sidebars by `link_to` (e.g. "Home Build Request"), so it
	// never finds a match and falls through to module-based switching. Patch
	// it to only run its original logic when the user is explicitly
	// navigating to a workspace URL.
	function patch_workspace_switch() {
		if (!frappe.app || !frappe.app.sidebar) return false;
		var sb = frappe.app.sidebar;
		if (sb._dcr_workspace_patched) return true;
		if (typeof sb.set_workspace_sidebar !== "function") return false;
		if (typeof sb.setup !== "function") return false;

		var original = sb.set_workspace_sidebar.bind(sb);
		var original_setup = sb.setup.bind(sb);

		sb.set_workspace_sidebar = function (router) {
			try {
				var route = frappe.get_route() || [];
				var slug = "";

				// Explicit workspace navigation looks like:
				//   /app/<workspace>                 -> route = ["workspace"]
				//   /app/Workspaces/<workspace>      -> route[0] = "Workspaces"
				//   /app/Workspaces/private/<name>   -> route[0] = "Workspaces"
				if (route.length === 1) {
					slug = (route[0] || "").toLowerCase();
				} else if (route.length >= 2 && (route[0] || "").toLowerCase() === "workspaces") {
					return original(router);
				}

				var is_workspace_nav = slug && !!workspace_from_slug(slug);

				// Let Frappe run its normal logic on first load (no
				// current sidebar yet) or when the user explicitly
				// navigates to a workspace.
				if (is_workspace_nav || !sb.sidebar_title) {
					return original(router);
				}

				// Otherwise keep the user on their current workspace —
				// just refresh which sidebar item is highlighted.
				sb.set_active_workspace_item();
			} catch (e) {
				console.log("DCR sidebar patch error:", e);
				return original(router);
			}
		};

		// Safety net: Frappe also invokes sidebar.setup(workspace) from
		// several other paths (toggle → set_sidebar_for_page, localStorage
		// replay in set_workspace_sidebar, module fallback, etc). If any
		// of those fire during a doctype navigation, block the rebuild
		// and just refresh highlighting instead.
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
				console.log("DCR sidebar setup-patch error:", e);
			}
			return original_setup(workspace_title);
		};

		sb._dcr_workspace_patched = true;
		sb._dcr_original_setup = original_setup;
		return true;
	}

	function try_patch_workspace_switch(n) {
		if (n <= 0) return;
		if (!patch_workspace_switch()) {
			setTimeout(function () { try_patch_workspace_switch(n - 1); }, 300);
		}
	}

	// -- Pick the right workspace on (hard) refresh --
	// On reload Frappe has no remembered workspace, so its module-based
	// fallback picks whichever workspace "owns" the doctype — usually the
	// wrong one (Access/Buying/Lending instead of Deals/Contacts). Choose
	// a candidate ourselves based on which workspaces actually list the
	// current doctype, preferring the last workspace the user was on.

	function find_candidate_workspaces(entity) {
		var map = frappe.boot.workspace_sidebar_item || {};
		var out = [];
		var target = normalize(entity);
		Object.keys(map).forEach(function (key) {
			var data = map[key];
			if (!data || !data.items) return;
			var matched = false;
			for (var i = 0; i < data.items.length && !matched; i++) {
				var item = data.items[i];
				if (item && normalize(item.link_to) === target) { matched = true; break; }
				var nested = (item && item.nested_items) || [];
				for (var j = 0; j < nested.length; j++) {
					if (nested[j] && normalize(nested[j].link_to) === target) { matched = true; break; }
				}
			}
			if (matched) out.push(data.label || key);
		});
		return out;
	}

	function workspace_slug_from_route(route) {
		// Frappe v16 routes a workspace as ["Workspaces", "<Name>"]; older
		// builds used a bare ["<slug>"]. Return the lowercase slug for
		// either form, or null if this isn't a workspace route.
		if (!route || !route.length) return null;
		if (route.length === 1 && route[0] && workspace_from_slug(route[0])) {
			return route[0].toLowerCase();
		}
		if (route.length >= 2 && (route[0] || "").toLowerCase() === "workspaces" && route[1]) {
			if ((route[1] || "").toLowerCase() === "private" && route[2]) {
				return route[2].toLowerCase();
			}
			return route[1].toLowerCase();
		}
		return null;
	}

	function pick_correct_workspace() {
		try {
			var route = frappe.get_route() || [];

			// Workspace URL — trust Frappe.
			var ws_slug = workspace_slug_from_route(route);
			if (ws_slug && workspace_from_slug(ws_slug)) return null;

			// Doctype entity — for list view ["List", "<DocType>"], form view
			// ["Form", "<DocType>", "<name>"], or a bare slug like
			// ["home-build-request"] pre-conversion.
			var entity = null;
			if (route.length >= 2) entity = route[1];
			else if (route.length === 1) entity = route[0];
			if (!entity) return null;

			var candidates = find_candidate_workspaces(entity);
			if (!candidates.length) return null;
			if (candidates.length === 1) return candidates[0];

			var entity_workspace = get_workspace_for_entity(entity, candidates);
			if (entity_workspace) return entity_workspace;

			var default_workspace = default_workspace_for_entity(entity, candidates);
			if (default_workspace) return default_workspace;

			var last = null;
			try { last = localStorage.getItem("dcr_last_workspace"); } catch (e) {}
			var last_workspace = candidate_label(last, candidates);
			if (last_workspace) return last_workspace;
			return candidates[0];
		} catch (e) {
			return null;
		}
	}

	function save_last_workspace(reason) {
		// Only save when the user is explicitly on a workspace URL. Saving
		// whatever sidebar_title currently is on a doctype page can persist
		// a buggy swap (e.g. "Access") and make every refresh keep it.
		try {
			var route = frappe.get_route() || [];
			var slug = workspace_slug_from_route(route);
			if (!slug) {
				console.info("[DCR sidebar] save skip", reason || "", { route: route });
				return false;
			}
			var workspace = workspace_from_slug(slug);
			if (!workspace) {
				console.info("[DCR sidebar] save no-map", reason || "", { slug: slug });
				return false;
			}
			localStorage.setItem("dcr_last_workspace", workspace.label);
			console.info("[DCR sidebar] saved", reason || "", workspace.label);
			return true;
		} catch (e) {
			console.log("[DCR sidebar] save error:", e);
			return false;
		}
	}

	function enforce_correct_workspace(reason) {
		if (!frappe.app || !frappe.app.sidebar) return;
		var sb = frappe.app.sidebar;
		var correct = pick_correct_workspace();
		console.info("[DCR sidebar] enforce", reason || "", {
			route: frappe.get_route(),
			current: sb.sidebar_title,
			correct: correct,
			last: localStorage.getItem("dcr_last_workspace"),
			patched: !!sb._dcr_workspace_patched
		});
		if (!correct) return;
		if (sb.sidebar_title === correct) return;
		var setup = sb._dcr_original_setup;
		if (typeof setup !== "function") {
			// Patch hasn't installed yet — fall back to the live setup,
			// which may be our patched version. The patched version blocks
			// switches on doctype views, so prefer the cached original
			// when available.
			if (typeof sb.setup === "function") setup = sb.setup.bind(sb);
		}
		if (typeof setup !== "function") return;
		try {
			console.info("[DCR sidebar] correcting", sb.sidebar_title, "→", correct);
			setup(correct);
		} catch (e) {
			console.log("[DCR sidebar] enforce error:", e);
		}
	}

	function enforce_retry(n) {
		if (n <= 0) return;
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar._dcr_workspace_patched) {
			enforce_correct_workspace("init");
		} else {
			setTimeout(function () { enforce_retry(n - 1); }, 300);
		}
	}

	function watch_sidebar_title() {
		// Last-resort safety net: if anything (Frappe internals, async
		// setup, our own slow correction) flips .body-sidebar's data-title
		// to the wrong workspace, revert it the moment the DOM mutates.
		var el = document.querySelector(".body-sidebar");
		if (!el) return false;
		if (el._dcr_title_watched) return true;
		el._dcr_title_watched = true;

		var reverting = false;
		var observer = new MutationObserver(function () {
			if (reverting) return;
			var current = el.getAttribute("data-title");
			var correct = pick_correct_workspace();
			if (!correct || current === correct) return;
			console.info("[DCR sidebar] data-title swap detected", current, "→ reverting to", correct);
			reverting = true;
			enforce_correct_workspace("title-mutation");
			setTimeout(function () { reverting = false; }, 100);
		});
		observer.observe(el, { attributes: true, attributeFilter: ["data-title"] });
		return true;
	}

	function try_watch_sidebar_title(n) {
		if (n <= 0) return;
		if (!watch_sidebar_title()) {
			setTimeout(function () { try_watch_sidebar_title(n - 1); }, 300);
		}
	}

	function inject_workspace_fullbleed_styles() {
		if (document.getElementById("dcr-workspace-fullbleed-js")) return;
		var style = document.createElement("style");
		style.id = "dcr-workspace-fullbleed-js";
		style.textContent = [
			"body.dcr-workspace-fullbleed { --page-max-width: none; --content-width: 100%; }",
			"body.dcr-workspace-fullbleed .main-section,",
			"body.dcr-workspace-fullbleed .page-container,",
			"body.dcr-workspace-fullbleed .page-wrapper,",
			"body.dcr-workspace-fullbleed .page-content,",
			"body.dcr-workspace-fullbleed .page-body,",
			"body.dcr-workspace-fullbleed .container.page-body,",
			"body.dcr-workspace-fullbleed .layout-main,",
			"body.dcr-workspace-fullbleed .layout-main-section-wrapper,",
			"body.dcr-workspace-fullbleed .layout-main-section,",
			"body.dcr-workspace-fullbleed .layout-main-section > .container,",
			"body.dcr-workspace-fullbleed .layout-main-section > .container-fluid,",
			"body.dcr-workspace-fullbleed .workspace-body,",
			"body.dcr-workspace-fullbleed .workspace-content,",
			"body.dcr-workspace-fullbleed .editor-js-container,",
			"body.dcr-workspace-fullbleed .codex-editor,",
			"body.dcr-workspace-fullbleed .codex-editor__redactor,",
			"body.dcr-workspace-fullbleed .ce-block,",
			"body.dcr-workspace-fullbleed .ce-block__content {",
			"  max-width: none !important;",
			"  width: 100% !important;",
			"  margin-left: 0 !important;",
			"  margin-right: 0 !important;",
			"  padding-left: 0 !important;",
			"  padding-right: 0 !important;",
			"}",
			"body.dcr-workspace-fullbleed .widget-group,",
			"body.dcr-workspace-fullbleed .widget-group-body,",
			"body.dcr-workspace-fullbleed .widget,",
			"body.dcr-workspace-fullbleed .number-card,",
			"body.dcr-workspace-fullbleed .chart-container,",
			"body.dcr-workspace-fullbleed .dashboard-section {",
			"  max-width: none !important;",
			"  width: 100% !important;",
			"}",
			"body.dcr-workspace-fullbleed .widget.custom-block-widget-box { padding: 0 !important; }"
		].join("\n");
		document.head.appendChild(style);
	}

	function set_workspace_fullbleed_class(reason) {
		try {
			var route = frappe.get_route() || [];
			var is_workspace = !!workspace_slug_from_route(route);
			if (!is_workspace && !route.length) {
				is_workspace = !!document.querySelector(".workspace-body");
			}
			document.body.classList.toggle("dcr-workspace-fullbleed", is_workspace);
			if (is_workspace) document.body.setAttribute("data-dcr-workspace-fullbleed", reason || "1");
			else document.body.removeAttribute("data-dcr-workspace-fullbleed");
		} catch (e) {
			console.log("[DCR sidebar] fullbleed class error:", e);
		}
	}

	// -- Init --

	function init() {
		var sb = document.querySelector(".body-sidebar-container");
		if (!sb) return false;
		if (_initialized) return true;
		_initialized = true;

		inject_workspace_fullbleed_styles();
		set_workspace_fullbleed_class("init");
		try_patch_workspace_switch(20);
		enforce_retry(20);
		try_watch_sidebar_title(20);
		$(window).on("beforeunload", function () { save_last_workspace("beforeunload"); });
		// Capture the initial workspace on hard refresh — frappe.router
		// emits its first "change" event before our handler attaches, so
		// save_last_workspace would otherwise never fire on cold load.
		// Multiple delayed attempts because frappe.get_route() may not be
		// populated yet at any single fixed offset; once one succeeds the
		// rest are no-ops (or harmlessly re-save the same label).
		[200, 600, 1500, 3000].forEach(function (ms) {
			setTimeout(function () { save_last_workspace("init+" + ms); }, ms);
			setTimeout(function () { set_workspace_fullbleed_class("init+" + ms); }, ms);
		});
		console.info("[DCR sidebar] init", { route: frappe.get_route() });

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
			set_workspace_fullbleed_class("route");
			setTimeout(function () { fix_active_retry(5); }, 300);
			// If Frappe's buggy swap slipped past our patch at any point,
			// correct the workspace after each navigation.
			setTimeout(function () { enforce_correct_workspace("route-200"); }, 200);
			setTimeout(function () { enforce_correct_workspace("route-600"); }, 600);
			setTimeout(function () { set_workspace_fullbleed_class("route-300"); }, 300);
			// Remember the workspace only when the user is explicitly on
			// a workspace URL (save_last_workspace guards against doctype
			// routes internally).
			setTimeout(function () { save_last_workspace("route-change"); }, 300);
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
