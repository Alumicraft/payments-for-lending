/**
 * Workspace Full-Width Override
 *
 * The user prefers Frappe's "Full Width" toggle OFF for forms and list
 * views, but workspace dashboards look cramped under the contained
 * width. This injects a CSS override on workspace routes only — forms
 * and lists stay contained.
 *
 * Detect "on a workspace page" via:
 *   route.length === 1 && route[0] is a known workspace slug
 *
 * The CSS is identical to the Map block's full-bleed treatment in
 * setup.py — kills max-width / padding on the layout containers
 * Frappe v16 wraps around .workspace-body.
 */
(function () {
    "use strict";

    var STYLE_ID = "dcr-workspace-fullwidth";

    var CSS = [
        "body .layout-main-section-wrapper,",
        "body .layout-main-section,",
        "body .layout-main-section > .container,",
        "body .layout-main-section > .container-fluid,",
        "body .layout-main-section .workspace-body {",
        "  max-width: none !important;",
        "  width: 100% !important;",
        "}",
        ".editor-js-container { max-width: none !important; }",
        ".ce-block__content { max-width: none !important; width: 100% !important; }"
    ].join("\n");

    function on_workspace_route() {
        var route = (frappe.get_route && frappe.get_route()) || [];
        if (route.length !== 1 || !route[0]) return false;
        var map = (frappe.boot && frappe.boot.workspace_sidebar_item) || {};
        return !!map[route[0].toLowerCase()];
    }

    function inject() {
        if (document.getElementById(STYLE_ID)) return;
        var style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }

    function remove() {
        var el = document.getElementById(STYLE_ID);
        if (el) el.remove();
    }

    function apply() {
        if (on_workspace_route()) inject();
        else remove();
    }

    function init() {
        apply();
        if (frappe.router && typeof frappe.router.on === "function") {
            frappe.router.on("change", apply);
        } else {
            $(document).on("page-change", apply);
        }
    }

    $(document).ready(init);
})();
