import frappe


def after_install():
    """Ensure DCR module definition and required groups exist."""
    # Map block first — isolated so any later setup failure cannot block it.
    try:
        ensure_map_block()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_map_block failed")

    if not frappe.db.exists("Module Def", "DCR"):
        frappe.get_doc({
            "doctype": "Module Def",
            "module_name": "DCR",
            "app_name": "dcr",
        }).insert(ignore_permissions=True)

    # Supplier Groups
    for group_name in ("Escrow", "Factory"):
        if not frappe.db.exists("Supplier Group", group_name):
            frappe.get_doc({
                "doctype": "Supplier Group",
                "supplier_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Customer Groups
    for group_name in ("Home Buyer", "Dealer"):
        if not frappe.db.exists("Customer Group", group_name):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Workspaces — created without a module so Frappe does not treat them
    # as "orphan" standard content and delete them during migrations.
    for ws in ("Overview", "Deals", "Accounting", "Contacts", "Access"):
        if not frappe.db.exists("Workspace", ws):
            frappe.get_doc({
                "doctype": "Workspace",
                "label": ws,
                "title": ws,
                "public": 1,
            }).insert(ignore_permissions=True)

    # Number Card: Users Online
    card_name = "Users Online"
    if not frappe.db.exists("Number Card", card_name):
        frappe.get_doc({
            "doctype": "Number Card",
            "name": card_name,
            "label": card_name,
            "type": "Custom",
            "method": "dcr.api.sessions.get_active_sessions",
            "is_public": 1,
            "owner": "Administrator",
        }).insert(ignore_permissions=True)

    # Dashboard Chart: Active Users Per Day
    chart_name = "Active Users Per Day"
    if not frappe.db.exists("Dashboard Chart", chart_name):
        frappe.get_doc({
            "doctype": "Dashboard Chart",
            "chart_name": chart_name,
            "chart_type": "Report",
            "report_name": "Daily Active Users",
            "x_field": "date",
            "filters_json": "{}",
            "type": "Line",
            "is_public": 1,
            "owner": "Administrator",
            "y_axis": [{"y_field": "active_users", "parentfield": "y_axis"}],
        }).insert(ignore_permissions=True)

    # NOTE: Number Card and Dashboard Chart are created above but NOT
    # added to the workspace programmatically.  Calling .save() on a
    # Workspace rebuilds its child tables from the `content` JSON field,
    # which wipes any cards/charts placed via the Workspace Builder.
    # Add them manually: Workspace Builder → Access → drag in the card/chart.

    # The patches.txt entry runs the LA-connections cleanup once; the
    # standard Lending app re-syncs Loan Application's DocType Links on
    # every migrate, which resets our changes. Re-apply post-migrate.
    try:
        tidy_la_connections()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "tidy_la_connections (after_install)")

    try:
        ensure_supplier_geo_fields()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_supplier_geo_fields failed")

    frappe.db.commit()


def ensure_supplier_geo_fields():
    """Create hidden latitude/longitude custom fields on Supplier.

    Used by the map block to plot factory icons. Hidden because they are
    populated automatically from the supplier's primary address — users
    should not edit them directly.
    """
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field

    fields = [
        {
            "fieldname": "latitude",
            "label": "Latitude",
            "fieldtype": "Float",
            "precision": "6",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "supplier_group",
        },
        {
            "fieldname": "longitude",
            "label": "Longitude",
            "fieldtype": "Float",
            "precision": "6",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "latitude",
        },
    ]
    for f in fields:
        if not frappe.db.exists("Custom Field", {"dt": "Supplier", "fieldname": f["fieldname"]}):
            create_custom_field("Supplier", f)


def tidy_la_connections():
    """Mirror dcr.patches.tidy_la_connections so it survives re-syncs.

    - Hide stock "Loan Security Assignment" link (DCR runs unsecured loans).
    - Group the stock "Loan" link under "Lending" so the LA connections
      panel renders with a header matching HBR's grouping.
    """
    lsa_links = frappe.get_all(
        "DocType Link",
        filters={
            "parent": "Loan Application",
            "parenttype": "DocType",
            "link_doctype": "Loan Security Assignment",
        },
        pluck="name",
    )
    for name in lsa_links:
        if not frappe.db.get_value("DocType Link", name, "hidden"):
            frappe.db.set_value("DocType Link", name, "hidden", 1)

    loan_links = frappe.get_all(
        "DocType Link",
        filters={
            "parent": "Loan Application",
            "parenttype": "DocType",
            "link_doctype": "Loan",
        },
        pluck="name",
    )
    for name in loan_links:
        if frappe.db.get_value("DocType Link", name, "group") != "Lending":
            frappe.db.set_value("DocType Link", name, "group", "Lending")

    frappe.clear_cache(doctype="Loan Application")


@frappe.whitelist()
def force_refresh_map_block():
    """Diagnostic: force re-run ensure_map_block and return live DB state.

    Call from browser console:
      frappe.call('dcr.setup.force_refresh_map_block').then(r => console.log(r.message))
    """
    frappe.only_for("System Manager")

    def snapshot(name):
        if not frappe.db.exists("Custom HTML Block", name):
            return None
        row = frappe.db.get_value(
            "Custom HTML Block", name,
            ["modified", "html", "script"], as_dict=True,
        )
        script = row.script or ""
        return {
            "name": name,
            "modified": str(row.modified),
            "html_preview": (row.html or "")[:120],
            "script_length": len(script),
            "script_head": script[:180],
            "script_tail": script[-180:] if len(script) > 180 else "",
        }

    js_field = None
    for candidate in ("script", "javascript", "js"):
        if frappe.db.has_column("Custom HTML Block", candidate):
            js_field = candidate
            break

    def workspace_refs():
        """Return {workspace_name: {mentions_map, mentions_legacy, snippet}} for
        any Workspace whose content references either block name."""
        out = {}
        for name in ("Map", "HBR Heatmap"):
            rows = frappe.get_all(
                "Workspace",
                filters={"content": ["like", f"%{name}%"]},
                pluck="name",
            )
            for ws in rows:
                if ws in out:
                    continue
                content = frappe.db.get_value("Workspace", ws, "content") or ""
                idx = content.find("HBR Heatmap")
                if idx == -1:
                    idx = content.find("Map")
                snippet = content[max(0, idx - 40):idx + 80] if idx != -1 else ""
                out[ws] = {
                    "mentions_map": "Map" in content,
                    "mentions_legacy": "HBR Heatmap" in content,
                    "snippet": snippet,
                }
        return out

    before = {
        "blocks": {
            "Map": snapshot("Map"),
            "HBR Heatmap": snapshot("HBR Heatmap"),
        },
        "workspaces": workspace_refs(),
    }

    error = None
    try:
        ensure_map_block()
        frappe.db.commit()
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        frappe.log_error(frappe.get_traceback(), "force_refresh_map_block")

    after = {
        "blocks": {
            "Map": snapshot("Map"),
            "HBR Heatmap": snapshot("HBR Heatmap"),
        },
        "workspaces": workspace_refs(),
    }

    return {
        "js_field_detected": js_field,
        "before": before,
        "after": after,
        "error": error,
    }


def ensure_map_block():
    """Create or update the workspace map Custom HTML Block."""
    block_name = "Map"
    legacy_block_name = "HBR Heatmap"

    # One-time migration from legacy name — rename the doc if the legacy name
    # is still present.
    if (
        frappe.db.exists("Custom HTML Block", legacy_block_name)
        and not frappe.db.exists("Custom HTML Block", block_name)
    ):
        frappe.rename_doc(
            "Custom HTML Block", legacy_block_name, block_name,
            force=True, merge=False,
        )

    # Patch Workspace content unconditionally. The workspace's `content` JSON
    # stores the block name as a raw string reference, and the rename above
    # does NOT propagate into that field. We keep this outside the rename
    # branch so a workspace left pointing at the legacy name (because the
    # rename ran successfully on an earlier migrate but the content patch
    # didn't match) still gets healed on the next boot.
    legacy_workspaces = frappe.get_all(
        "Workspace",
        filters={"content": ["like", f"%{legacy_block_name}%"]},
        pluck="name",
    )
    for ws in legacy_workspaces:
        content = frappe.db.get_value("Workspace", ws, "content") or ""
        if legacy_block_name in content:
            frappe.db.set_value(
                "Workspace", ws, "content",
                content.replace(legacy_block_name, block_name),
            )
            frappe.clear_document_cache("Workspace", ws)
    if legacy_workspaces:
        frappe.db.commit()

    html_content = """<style>
.mapboxgl-ctrl-bottom-left, .mapboxgl-ctrl-bottom-right { transform: translateY(150%); }

/* DCR map popup styling — see docs/superpowers/specs/2026-04-30-map-icons-and-trails.md */
.mapboxgl-popup-content { padding: 0; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 14px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.04); }
.mapboxgl-popup--dark .mapboxgl-popup-content { background: #1C1F23; box-shadow: 0 6px 18px rgba(0,0,0,0.5), 0 0 0 1px #2D3137; }
.mapboxgl-popup--dark .mapboxgl-popup-tip { border-top-color: #1C1F23; border-bottom-color: #1C1F23; }
.mapboxgl-popup-close-button { font-size: 18px; padding: 4px 8px; color: inherit; }

.dcr-popup { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 13px; line-height: 1.45; color: #1F272E; min-width: 320px; }
.dcr-popup--dark { color: #F2F4F5; }
.dcr-popup--multi { width: 380px; }
.dcr-popup--factory { width: 320px; }

.dcr-popup__header { padding: 14px 16px 10px; }
.dcr-popup__title { font-size: 15px; font-weight: 600; margin: 0 0 2px; }
.dcr-popup__subtitle { font-size: 13px; font-weight: 500; margin: 0; }
.dcr-popup__tertiary { font-size: 12px; font-weight: 500; margin: 2px 0 0; }
.dcr-popup__body { padding: 6px 16px 14px; }
.dcr-popup__footer { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #ECEDEE; }
.dcr-popup--dark .dcr-popup__footer { border-top-color: #2D3137; }

.dcr-popup .text-secondary { color: #687178; }
.dcr-popup--dark .text-secondary { color: #A6ADB4; }
.dcr-popup .link { color: #2490EF; text-decoration: none; }
.dcr-popup--dark .link { color: #4DA8FF; }
.dcr-popup .link:hover { text-decoration: underline; }

.dcr-popup .field-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 6px 0; }
.dcr-popup .field-row .label-text { flex-shrink: 0; font-weight: 500; }
.dcr-popup .field-row .value-text { text-align: right; font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dcr-popup .hbr-id { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }

.dcr-popup .pill { display: inline-flex; align-items: center; padding: 3px 8px; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; border-radius: 4px; line-height: 1.2; }
.dcr-popup .pill--pending  { background: rgba(104,113,120,0.16); color: #5A6166; }
.dcr-popup--dark .pill--pending { background: rgba(166,173,180,0.18); color: #C8CFD5; }
.dcr-popup .pill--ordered  { background: rgba(255,123,0,0.16); color: #D96D00; }
.dcr-popup--dark .pill--ordered { background: rgba(255,154,60,0.20); color: #FFB066; }
.dcr-popup .pill--delivered { background: linear-gradient(135deg,#007AFF 0%,#0074F3 100%); color: #FFFFFF; }
.dcr-popup--dark .pill--delivered { background: linear-gradient(135deg,#4DA8FF 0%,#3F9EE8 100%); color: #0E1116; }

.dcr-popup .btn { flex: 1; padding: 8px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; text-align: center; cursor: pointer; border: none; font-family: inherit; transition: opacity .12s ease, background .12s ease; }
.dcr-popup .btn:active { transform: translateY(1px); }
.dcr-popup .btn--primary { background: linear-gradient(135deg,#007AFF 0%,#0074F3 100%); color: #fff; }
.dcr-popup .btn--primary:hover { opacity: .92; }
.dcr-popup--dark .btn--primary { background: linear-gradient(135deg,#4DA8FF 0%,#3F9EE8 100%); color: #0E1116; }
.dcr-popup .btn--secondary { background: #F2F3F4; color: #1F272E; }
.dcr-popup .btn--secondary:hover { background: #E8EAEC; }
.dcr-popup--dark .btn--secondary { background: #2D3137; color: #F2F4F5; }
.dcr-popup--dark .btn--secondary:hover { background: #383D42; }

.dcr-popup .stack-list { padding: 4px 0; border-top: 1px solid #ECEDEE; }
.dcr-popup--dark .stack-list { border-top-color: #2D3137; }
.dcr-popup .stack-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 10px 16px; align-items: center; cursor: pointer; transition: background .12s ease; }
.dcr-popup .stack-row:hover { background: #FAFAFA; }
.dcr-popup--dark .stack-row:hover { background: #22272B; }
.dcr-popup .stack-row + .stack-row { border-top: 1px solid #F0F0F0; }
.dcr-popup--dark .stack-row + .stack-row { border-top-color: #2A2E33; }
.dcr-popup .stack-row__head { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; min-width: 0; }
.dcr-popup .stack-row__customer { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.dcr-popup .stack-row__factory { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dcr-popup .stack-row__meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.dcr-popup .stack-row__space { font-size: 11px; font-weight: 500; }
.dcr-popup .trail-btn { width: 24px; height: 24px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; background: transparent; border: 1px solid #C7CDD3; color: #687178; padding: 0; opacity: .55; transition: opacity .12s ease, background .12s ease; }
.dcr-popup .trail-btn:hover { opacity: 1; background: #F2F3F4; }
.dcr-popup--dark .trail-btn { border-color: #4A5158; color: #A6ADB4; }
.dcr-popup--dark .trail-btn:hover { background: #2D3137; }
.dcr-popup .trail-btn svg { width: 12px; height: 12px; }

.dcr-popup .stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; padding: 14px 16px 4px; border-top: 1px solid #ECEDEE; }
.dcr-popup--dark .stats { border-top-color: #2D3137; }
.dcr-popup .stat { display: flex; flex-direction: column; gap: 6px; }
.dcr-popup .stat__count { font-size: 22px; font-weight: 700; line-height: 1; }
.dcr-popup .stat__label { display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; }
.dcr-popup .stat__dot { width: 8px; height: 8px; border-radius: 50%; }
.dcr-popup .dot--pending { background: #687178; }
.dcr-popup .dot--ordered { background: #FF7B00; }
.dcr-popup .dot--delivered { background: linear-gradient(135deg,#007AFF,#0074F3); }
.dcr-popup--dark .dot--delivered { background: linear-gradient(135deg,#4DA8FF,#3F9EE8); }
.dcr-popup .factory-total { padding: 6px 16px 12px; font-size: 12px; font-weight: 500; }

/* Legend */
.dcr-legend { position: absolute; bottom: 16px; left: 16px; z-index: 5; background: #fff; border-radius: 10px; box-shadow: 0 2px 12px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.04); padding: 10px 12px; min-width: 200px; font-family: 'Inter', -apple-system, sans-serif; font-size: 12px; }
.dcr-legend--dark { background: #1C1F23; color: #F2F4F5; box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px #2D3137; }
.dcr-legend__title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; color: #687178; margin-bottom: 8px; }
.dcr-legend--dark .dcr-legend__title { color: #A6ADB4; }
.dcr-legend__row { display: grid; grid-template-columns: 16px 1fr auto auto; gap: 8px; align-items: center; padding: 4px 0; cursor: pointer; user-select: none; }
.dcr-legend__row.is-off { opacity: .4; }
.dcr-legend__swatch { width: 12px; height: 12px; border-radius: 50%; }
.dcr-legend .dot--pending { background: #687178; }
.dcr-legend .dot--ordered { background: #FF7B00; }
.dcr-legend .dot--delivered { background: linear-gradient(135deg,#007AFF,#0074F3); }
.dcr-legend--dark .dot--delivered { background: linear-gradient(135deg,#4DA8FF,#3F9EE8); }
.dcr-legend__count { font-variant-numeric: tabular-nums; color: #687178; }
.dcr-legend--dark .dcr-legend__count { color: #A6ADB4; }
.dcr-legend__check { width: 14px; height: 14px; }
.dcr-legend__footer { margin-top: 6px; padding-top: 6px; border-top: 1px solid #ECEDEE; display: flex; gap: 8px; font-size: 11px; }
.dcr-legend--dark .dcr-legend__footer { border-top-color: #2D3137; }
.dcr-legend__footer a { color: #2490EF; cursor: pointer; }
.dcr-legend--dark .dcr-legend__footer a { color: #4DA8FF; }

/* Block view: read-only legend pill */
.dcr-legend--block { padding: 6px 10px; min-width: 0; display: flex; gap: 12px; align-items: center; }
.dcr-legend--block .dcr-legend__title { display: none; }
.dcr-legend--block .dcr-legend__row { display: flex; gap: 6px; padding: 0; cursor: default; }
.dcr-legend--block .dcr-legend__check, .dcr-legend--block .dcr-legend__count { display: none; }
</style>
<div id="dcr-map" style="width:100%; overflow: hidden; position: relative;"></div>"""

    js_content = r"""
(function() {
    var container = root_element.querySelector('#dcr-map');
    if (!container) return;

    // Full-bleed on Map workspace, rounded corners elsewhere
    var isMapPage = (frappe.get_route() || []).join('/').toLowerCase().indexOf('map') !== -1;
    if (!isMapPage) {
        container.style.borderRadius = 'var(--border-radius-lg)';
    }
    if (isMapPage && !document.getElementById('dcr-map-fullbleed')) {
        var style = document.createElement('style');
        style.id = 'dcr-map-fullbleed';
        style.textContent = [
            // Kill max-width on every layout container Frappe v16 might put
            // around the content when the workspace is NOT in full-width
            // mode. This way the user doesn't have to toggle Full Width on
            // the Map workspace for the map to stretch edge-to-edge.
            'body .layout-main-section-wrapper,',
            'body .layout-main-section,',
            'body .layout-main-section > .container,',
            'body .layout-main-section > .container-fluid,',
            'body .layout-main-section .workspace-body {',
            '  max-width: none !important;',
            '  width: 100% !important;',
            '  padding: 0 !important;',
            '  margin: 0 !important;',
            '}',
            '.editor-js-container { margin: 0 !important; max-width: none !important; }',
            '.codex-editor__redactor { padding-bottom: 0 !important; }',
            '.ce-block__content { max-width: none !important; width: 100% !important; padding: 0 !important; }',
            '.ce-block.col-xs-12 { padding: 0 !important; }',
            '.widget.custom-block-widget-box { padding: 0 !important; max-width: none !important; }'
        ].join('\n');
        document.head.appendChild(style);

        // Remove fullbleed styles when navigating away
        frappe.router.on('change', function() {
            var stillMap = (frappe.get_route() || []).join('/').toLowerCase().indexOf('map') !== -1;
            if (!stillMap) {
                var el = document.getElementById('dcr-map-fullbleed');
                if (el) el.remove();
                // Stop the trail rAF — without this, animation keeps running
                // against an orphaned map after the user leaves the workspace.
                if (window._dcrClearTrail) window._dcrClearTrail();
            }
        });
    }

    // Dynamic height: fill from container top to bottom of viewport
    function setHeight() {
        var rect = container.getBoundingClientRect();
        container.style.height = (window.innerHeight - rect.top) + 'px';
    }
    setHeight();
    window.addEventListener('resize', setHeight);

    // Idempotent doc-level listener registration. Frappe re-runs this IIFE
    // whenever the workspace remounts; without this, every navigation back
    // to the Map workspace would attach a fresh handler.
    function registerDocListener(key, type, handler) {
        var existing = window['_dcr' + key];
        if (existing) document.removeEventListener(type, existing);
        document.addEventListener(type, handler);
        window['_dcr' + key] = handler;
    }

    // Load Mapbox GL JS
    function loadMapbox(cb) {
        // Inject CSS into shadow root so it reaches the controls
        var shadowRoot = container.getRootNode();
        if (shadowRoot && !shadowRoot.querySelector('.mapboxgl-css')) {
            var css = document.createElement('link');
            css.rel = 'stylesheet';
            css.href = 'https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css';
            css.className = 'mapboxgl-css';
            shadowRoot.appendChild(css);
        }
        // Also load in document.head as fallback
        if (!document.querySelector('.mapboxgl-css')) {
            var css2 = document.createElement('link');
            css2.rel = 'stylesheet';
            css2.href = 'https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css';
            css2.className = 'mapboxgl-css';
            document.head.appendChild(css2);
        }
        if (window.mapboxgl) { cb(); return; }
        var s = document.createElement('script');
        s.src = 'https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.js';
        s.onload = cb;
        document.head.appendChild(s);
    }

    function initMap() {
        frappe.call({
            method: 'dcr.api.map.get_map_settings',
            callback: function(r) {
                if (!r.message || !r.message.access_token) {
                    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8d99a6;font-size:14px;">Configure Map Settings to enable the heatmap</div>';
                    return;
                }
                var cfg = r.message;
                mapboxgl.accessToken = cfg.access_token;
                // Block view zooms out a bit so the smaller widget still
                // shows context; full-bleed Map workspace uses default_zoom.
                var initialZoom = isMapPage ? cfg.default_zoom : (cfg.block_zoom || cfg.default_zoom);
                var puckFullThreshold = cfg.puck_full_zoom_threshold || 12;
                var map = new mapboxgl.Map({
                    container: container,
                    style: cfg.map_style_url,
                    center: [cfg.default_longitude, cfg.default_latitude],
                    zoom: initialZoom
                });
                window._dcrMap = map;
                map.addControl(new mapboxgl.NavigationControl(), 'top-right');

                // 3D toggle control
                var ThreeDControl = function() {};
                ThreeDControl.prototype.onAdd = function(m) {
                    this._map = m;
                    this._container = document.createElement('div');
                    this._container.className = 'mapboxgl-ctrl mapboxgl-ctrl-group';
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.title = 'Toggle 3D';
                    btn.style.fontWeight = '600';
                    btn.style.fontSize = '11px';
                    btn.textContent = '3D';
                    btn.onclick = function() {
                        var is3D = m.getPitch() > 0;
                        if (is3D) {
                            m.easeTo({ pitch: 0, bearing: 0 });
                            btn.textContent = '3D';
                            btn.classList.remove('active');
                        } else {
                            m.easeTo({ pitch: 60, bearing: -15 });
                            btn.textContent = '2D';
                            btn.classList.add('active');
                        }
                    };
                    this._container.appendChild(btn);
                    return this._container;
                };
                ThreeDControl.prototype.onRemove = function() {
                    this._container.parentNode.removeChild(this._container);
                    this._map = undefined;
                };
                map.addControl(new ThreeDControl(), 'top-right');

                // Recenter control
                var RecenterControl = function() {};
                RecenterControl.prototype.onAdd = function(m) {
                    this._container = document.createElement('div');
                    this._container.className = 'mapboxgl-ctrl mapboxgl-ctrl-group';
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.title = 'Recenter';
                    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="display:block;margin:auto;"><path d="M3 11L12 3L21 11V20C21 20.5523 20.5523 21 20 21H15V14H9V21H4C3.44772 21 3 20.5523 3 20V11Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/></svg>';
                    btn.onclick = function() {
                        m.easeTo({
                            center: [cfg.default_longitude, cfg.default_latitude],
                            zoom: initialZoom,
                            pitch: 0,
                            bearing: 0,
                            duration: 2500
                        });
                    };
                    this._container.appendChild(btn);
                    return this._container;
                };
                RecenterControl.prototype.onRemove = function() {
                    this._container.parentNode.removeChild(this._container);
                };
                map.addControl(new RecenterControl(), 'top-right');

                // Day/night mode + icon swap based on Frappe theme
                var _pinsLoaded = false;
                function syncTheme() {
                    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    try { map.setConfigProperty('basemap', 'lightPreset', isDark ? 'night' : 'day'); } catch(e) {}
                    if (_pinsLoaded && map.getLayer('unclustered-point')) {
                        map.setLayoutProperty(
                            'unclustered-point', 'icon-image',
                            iconImageExpr(currentTheme(), puckFullThreshold)
                        );
                    }

                    // Theme the Mapbox controls (zoom, compass, 3D, recenter).
                    // Lives inside the shadow root so these rules actually reach
                    // the controls — desk-level CSS can't pierce the shadow.
                    var shadowRoot = container.getRootNode();
                    if (shadowRoot && shadowRoot.appendChild) {
                        var styleEl = shadowRoot.querySelector && shadowRoot.querySelector('#dcr-map-ctrl-theme');
                        if (!styleEl) {
                            styleEl = document.createElement('style');
                            styleEl.id = 'dcr-map-ctrl-theme';
                            shadowRoot.appendChild(styleEl);
                        }
                        styleEl.textContent = isDark ? [
                            '.mapboxgl-ctrl-group {',
                            '  background: #1e293b !important;',
                            '  box-shadow: 0 0 0 2px rgba(0,0,0,0.2);',
                            '}',
                            '.mapboxgl-ctrl-group button {',
                            '  background-color: transparent;',
                            '  color: #e2e8f0;',
                            '}',
                            '.mapboxgl-ctrl-group button:not(:disabled):hover {',
                            '  background-color: #334155 !important;',
                            '}',
                            '.mapboxgl-ctrl-group button + button {',
                            '  border-top: 1px solid #334155;',
                            '}',
                            '.mapboxgl-ctrl-group button.active {',
                            '  background-color: #1e3a5f !important;',
                            '  color: #93c5fd;',
                            '}',
                            '.mapboxgl-ctrl-icon {',
                            '  filter: invert(1) brightness(1.1);',
                            '}'
                        ].join('\n') : [
                            '.mapboxgl-ctrl-group button.active {',
                            '  background-color: #e7f1ff !important;',
                            '  color: #1d4ed8;',
                            '}'
                        ].join('\n');
                    }
                    var legendEl = container.querySelector('.dcr-legend');
                    if (legendEl) {
                        legendEl.classList.toggle('dcr-legend--dark', isDark);
                    }
                }
                map.on('style.load', syncTheme);

                // Watch for Frappe theme changes
                var themeObserver = new MutationObserver(syncTheme);
                themeObserver.observe(document.documentElement, {
                    attributes: true, attributeFilter: ['data-theme']
                });

                map.on('load', function() {
                    map.addSource('dcr-trails', {
                        type: 'geojson',
                        data: { type: 'FeatureCollection', features: [] }
                    });
                    map.addLayer({
                        id: 'dcr-trails',
                        type: 'line',
                        source: 'dcr-trails',
                        layout: { 'line-cap': 'round', 'line-join': 'round' },
                        paint: {
                            'line-color': ['get', 'color'],
                            'line-width': 2.5,
                            'line-dasharray': [0, 4, 3]
                        }
                    });
                    loadData(map);
                    loadFactories(map);
                });

                map.on('click', function(e) {
                    var hits = map.queryRenderedFeatures(e.point, {
                        layers: ['unclustered-point', 'factory-point']
                    });
                    if (hits.length) return;  // pin click already handled
                    if (_activePopup) _activePopup.remove();
                    setTrailFeatures([]);
                });
            }
        });
    }

    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    // Puck under threshold, full pin at/above. Status drives the suffix.
    // Match keys are Title Case (matches GeoJSON properties.status); image
    // suffixes are lowercase (match disk filenames). Don't swap the cases.
    function iconImageExpr(theme, threshold) {
        var prefix = function(style) {
            return [
                'match', ['get', 'status'],
                'Ordered',   'home-' + style + '-' + theme + '-ordered',
                'Delivered', 'home-' + style + '-' + theme + '-delivered',
                /* default Pending */ 'home-' + style + '-' + theme + '-pending'
            ];
        };
        return ['step', ['zoom'], prefix('puck'), threshold, prefix('full')];
    }

    function iconSizeExpr(threshold) {
        // Pucks are smaller assets, render at 0.5; full pins at 0.212 (matches
        // existing scale tuned for the previous pin asset).
        return ['step', ['zoom'], 0.5, threshold, 0.212];
    }

    function iconAnchorExpr(threshold) {
        // Pucks anchor at center, full pins at bottom (the point of the pin).
        return ['step', ['zoom'], 'center', threshold, 'bottom'];
    }

    // Active statuses; defaults to all three. Task 9 wires legend ↔ filter
    // ↔ localStorage. Until then this returns the always-pass filter.
    function currentStatusFilter() {
        var active = window._dcrMapActiveStatuses || ['Pending', 'Ordered', 'Delivered'];
        return ['in', ['get', 'status'], ['literal', active]];
    }

    // ========== POPUP HELPERS =========================================
    function popupClass() {
        return currentTheme() === 'dark' ? 'mapboxgl-popup--dark' : '';
    }
    function popupRootClass() {
        return 'dcr-popup' + (currentTheme() === 'dark' ? ' dcr-popup--dark' : '');
    }
    function escHtml(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, function(c) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
        });
    }
    function relativeDays(iso) {
        if (!iso) return '';
        var t = new Date(iso).getTime();
        if (isNaN(t)) return '';
        var days = Math.floor((Date.now() - t) / 86400000);
        if (days < 1) return 'today';
        if (days === 1) return '1 day ago';
        if (days < 30) return days + ' days ago';
        if (days < 60) return '1 month ago';
        if (days < 365) return Math.floor(days / 30) + ' months ago';
        return Math.floor(days / 365) + 'y ago';
    }
    function statusPillHtml(status) {
        // Status is a closed set ('Pending'|'Ordered'|'Delivered') from
        // dcr.api.map._derive_status; lowercasing produces a safe class name.
        // If user-supplied status strings are ever introduced, sanitize before
        // concatenating into the class attribute.
        var s = (status || 'Pending').toLowerCase();
        return '<span class="pill pill--' + s + '">' + escHtml(status || 'Pending') + '</span>';
    }
    function trailBtnSvg() {
        return '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">'
            +  '<path d="M2 6 Q6 2, 10 6"/><circle cx="2" cy="6" r="1.2" fill="currentColor"/>'
            +  '<circle cx="10" cy="6" r="1.2" fill="currentColor"/></svg>';
    }
    function tertiaryLine(props) {
        var bits = [];
        if (props.space_number) bits.push('Space ' + props.space_number);
        var loc = [props.city, props.state].filter(Boolean).join(', ');
        if (loc && props.zip) loc += ' ' + props.zip;
        if (loc) bits.push(loc);
        return bits.join(' · ');
    }

    // Single popup at a time — track and dismiss on switch
    var _activePopup = null;
    function openPopup(map, lngLat, html, opts) {
        if (_activePopup) _activePopup.remove();
        var p = new mapboxgl.Popup(Object.assign({
            offset: 16,
            className: popupClass(),
            anchor: 'auto',
            maxWidth: '420px'
        }, opts || {}));
        p.setLngLat(lngLat).setHTML(html).addTo(map);
        p.on('close', function() {
            if (_activePopup === p) _activePopup = null;
            // Trail dismiss on popup close — Task 8 hooks here
            if (window._dcrClearTrail) window._dcrClearTrail();
        });
        _activePopup = p;
        return p;
    }

    // ========== RENDERERS =============================================
    function renderSingleHomeHtml(props, home) {
        // `props` is the GeoJSON feature properties (the group level);
        // `home` is the single home record from props.homes_json.
        var rows = [
            ['Status',   statusPillHtml(home.status)],
            ['Customer', home.customer_name
                ? escHtml(home.customer_name) + ' · <a class="link" href="/app/customer/' + encodeURIComponent(home.customer || '') + '" target="_top">View</a>'
                : '<span class="text-secondary">—</span>'],
            ['Factory',  home.factory_name
                ? escHtml(home.factory_name) + ' · <a class="link" href="/app/supplier/' + encodeURIComponent(home.factory || '') + '" target="_top">View</a>'
                : '<span class="text-secondary">—</span>'],
            ['HBR',      '<span class="hbr-id">' + escHtml(home.name) + '</span>'],
            ['Created',  '<span class="text-secondary">' + escHtml(relativeDays(home.creation_iso)) + '</span>'],
        ];
        return '<div class="' + popupRootClass() + '">'
            +    '<div class="dcr-popup__header">'
            +      '<h3 class="dcr-popup__title">' + escHtml(props.address || '') + '</h3>'
            +      (props.community_name ? '<p class="dcr-popup__subtitle text-secondary">' + escHtml(props.community_name) + '</p>' : '')
            +      (tertiaryLine(props) ? '<p class="dcr-popup__tertiary text-secondary">' + escHtml(tertiaryLine(props)) + '</p>' : '')
            +    '</div>'
            +    '<div class="dcr-popup__body">'
            +      rows.map(function(r) {
                     return '<div class="field-row"><span class="label-text text-secondary">' + r[0] + '</span><span class="value-text">' + r[1] + '</span></div>';
                   }).join('')
            +    '</div>'
            +    '<div class="dcr-popup__footer">'
            +      '<button class="btn btn--primary" data-act="open-hbr" data-name="' + escHtml(home.name) + '">Open HBR</button>'
            +      '<button class="btn btn--secondary" data-act="show-trail" data-name="' + escHtml(home.name) + '">Show trail</button>'
            +    '</div>'
            +  '</div>';
    }

    function renderStackedHtml(props, homes) {
        var rowsHtml = homes.map(function(h, i) {
            var ageBit = h.creation_iso ? ' · ' + escHtml(relativeDays(h.creation_iso)) : '';
            return '<div class="stack-row" role="button" tabindex="0" data-act="drill" data-idx="' + i + '">'
                +    '<div class="stack-row__main">'
                +      '<div class="stack-row__head">'
                +        statusPillHtml(h.status)
                +        '<span class="stack-row__customer">' + escHtml(h.customer_name || '—') + '</span>'
                +      '</div>'
                +      '<div class="stack-row__factory text-secondary">' + escHtml(h.factory_name || '—') + ageBit + '</div>'
                +    '</div>'
                +    '<div class="stack-row__meta">'
                +      (props.space_number ? '<span class="stack-row__space text-secondary">Space ' + escHtml(props.space_number) + '</span>' : '')
                +      '<button class="trail-btn" data-act="show-trail" data-name="' + escHtml(h.name) + '" title="Show trail">' + trailBtnSvg() + '</button>'
                +    '</div>'
                +  '</div>';
        }).join('');
        var loc = [props.city, props.state].filter(Boolean).join(', ');
        return '<div class="' + popupRootClass() + ' dcr-popup--multi">'
            +    '<div class="dcr-popup__header">'
            +      '<h3 class="dcr-popup__title">' + homes.length + ' deals at ' + escHtml(props.address || '') + '</h3>'
            +      (props.community_name || loc ? '<p class="dcr-popup__subtitle text-secondary">' + escHtml([props.community_name, loc].filter(Boolean).join(' · ')) + '</p>' : '')
            +    '</div>'
            +    '<div class="stack-list">' + rowsHtml + '</div>'
            +    '<div class="dcr-popup__footer">'
            +      '<button class="btn btn--secondary" data-act="open-list" style="flex:1;">Open all in list view</button>'
            +    '</div>'
            +  '</div>';
    }

    function renderFactoryHtml(props) {
        return '<div class="' + popupRootClass() + ' dcr-popup--factory">'
            +    '<div class="dcr-popup__header">'
            +      '<h3 class="dcr-popup__title">' + escHtml(props.supplier_name || props.name) + '</h3>'
            +      (props.city ? '<p class="dcr-popup__subtitle text-secondary">' + escHtml(props.city) + '</p>' : '')
            +    '</div>'
            +    '<div class="stats">'
            +      '<div class="stat"><span class="stat__count">' + (props.pending_count || 0) + '</span><span class="stat__label text-secondary"><span class="stat__dot dot--pending"></span>Pending</span></div>'
            +      '<div class="stat"><span class="stat__count">' + (props.ordered_count || 0) + '</span><span class="stat__label text-secondary"><span class="stat__dot dot--ordered"></span>Ordered</span></div>'
            +      '<div class="stat"><span class="stat__count">' + (props.delivered_count || 0) + '</span><span class="stat__label text-secondary"><span class="stat__dot dot--delivered"></span>Delivered</span></div>'
            +    '</div>'
            +    '<div class="factory-total text-secondary">' + (props.total_12mo || 0) + ' deals routed here in the last 12 months</div>'
            +    '<div class="dcr-popup__footer">'
            +      '<button class="btn btn--primary" data-act="open-supplier" data-name="' + escHtml(props.name) + '">Open Supplier</button>'
            +      '<button class="btn btn--secondary" data-act="show-all-trails" data-name="' + escHtml(props.name) + '">Show all trails</button>'
            +    '</div>'
            +  '</div>';
    }

    // Delegate clicks inside any open popup. Registered idempotently so
    // SPA re-mount doesn't accumulate handlers.
    registerDocListener('PopupClick', 'click', function(e) {
        var t = e.target.closest('[data-act]');
        if (!t || !_activePopup) return;
        var act = t.getAttribute('data-act');
        var name = t.getAttribute('data-name');
        if (act === 'open-hbr' && name) {
            window.open('/app/home-build-request/' + encodeURIComponent(name), '_top');
        } else if (act === 'open-supplier' && name) {
            window.open('/app/supplier/' + encodeURIComponent(name), '_top');
        } else if (act === 'open-list') {
            var p = _activePopup._dcrProps;
            if (p && p.address) {
                window.open('/app/home-build-request?delivery_address=' + encodeURIComponent(p.address), '_top');
            }
        } else if (act === 'drill') {
            var p2 = _activePopup._dcrProps;
            var homes = _activePopup._dcrHomes;
            var idx = parseInt(t.getAttribute('data-idx'), 10);
            if (p2 && homes && homes[idx]) drillIntoHome(p2, homes[idx]);
        } else if (act === 'show-trail' && name) {
            if (window._dcrShowTrailForHome) window._dcrShowTrailForHome(name);
        } else if (act === 'show-all-trails' && name) {
            if (window._dcrShowFactoryFan) window._dcrShowFactoryFan(name);
        }
    });

    // Esc dismisses popup + trail
    registerDocListener('PopupKey', 'keydown', function(e) {
        if (e.key === 'Escape') {
            if (_activePopup) _activePopup.remove();
            setTrailFeatures([]);
        }
    });

    function drillIntoHome(groupProps, home) {
        // Open the single-home popup at the same lngLat with anchor:auto so
        // Mapbox repositions to the side with the most viewport room.
        var lngLat = _activePopup.getLngLat();
        var html = renderSingleHomeHtml(groupProps, home);
        var p = openPopup(window._dcrMap, lngLat, html, { anchor: 'auto', offset: 16 });
        p._dcrProps = groupProps;
        p._dcrHomes = [home];
    }

    // ========== TRAIL HELPERS =========================================
    // Great-circle interpolation (slerp on the unit sphere). N segments → N+1 points.
    function greatCircleLine(start, end, n) {
        var lon1 = start[0] * Math.PI / 180, lat1 = start[1] * Math.PI / 180;
        var lon2 = end[0]   * Math.PI / 180, lat2 = end[1]   * Math.PI / 180;
        var d = 2 * Math.asin(Math.sqrt(
            Math.pow(Math.sin((lat2-lat1)/2), 2) +
            Math.cos(lat1)*Math.cos(lat2)*Math.pow(Math.sin((lon2-lon1)/2), 2)
        ));
        if (d === 0) return [start, end];
        var coords = [];
        for (var i = 0; i <= n; i++) {
            var f = i / n;
            var A = Math.sin((1-f)*d)/Math.sin(d);
            var B = Math.sin(f*d)/Math.sin(d);
            var x = A*Math.cos(lat1)*Math.cos(lon1) + B*Math.cos(lat2)*Math.cos(lon2);
            var y = A*Math.cos(lat1)*Math.sin(lon1) + B*Math.cos(lat2)*Math.sin(lon2);
            var z = A*Math.sin(lat1) + B*Math.sin(lat2);
            var lat = Math.atan2(z, Math.sqrt(x*x + y*y));
            var lon = Math.atan2(y, x);
            coords.push([lon * 180 / Math.PI, lat * 180 / Math.PI]);
        }
        return coords;
    }

    var STATUS_COLOR = {
        Pending:   '#687178',
        Ordered:   '#FF7B00',
        Delivered: '#007AFF'
    };

    // ========== TRAIL SOURCE/LAYER ====================================
    var _trailRAF = null;
    var _trailOffset = 0;
    var _factoryByName = {};

    window._dcrIndexFactory = function(d) {
        // Called from loadFactories' GeoJSON map step.
        if (!d || !d.name) return;
        _factoryByName[d.name] = d;
    };

    function setTrailFeatures(features) {
        var src = window._dcrMap && window._dcrMap.getSource('dcr-trails');
        if (!src) return;
        src.setData({ type: 'FeatureCollection', features: features });
        if (features.length && !_trailRAF) startTrailAnimation();
        if (!features.length && _trailRAF) stopTrailAnimation();
    }
    function startTrailAnimation() {
        function step() {
            _trailOffset = (_trailOffset + 0.4) % 7;
            try {
                window._dcrMap.setPaintProperty('dcr-trails', 'line-dasharray',
                    [_trailOffset, 4, 3]);
            } catch(_) {}
            _trailRAF = requestAnimationFrame(step);
        }
        _trailRAF = requestAnimationFrame(step);
    }
    function stopTrailAnimation() {
        if (_trailRAF) cancelAnimationFrame(_trailRAF);
        _trailRAF = null;
        _trailOffset = 0;
    }
    window._dcrClearTrail = function() { setTrailFeatures([]); };

    function trailFeatureForHome(homeProps, home) {
        if (!home || !home.factory) return null;
        var fac = _factoryByName[home.factory];
        if (!fac) return null;
        var start = [Number(homeProps.longitude) || 0, Number(homeProps.latitude) || 0];
        var end   = [fac.longitude, fac.latitude];
        var coords = greatCircleLine(start, end, 24);
        return {
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: coords },
            properties: { color: STATUS_COLOR[home.status] || STATUS_COLOR.Pending }
        };
    }

    window._dcrShowTrailForHome = function(homeName) {
        if (!_activePopup) return;
        var props = _activePopup._dcrProps;
        var homes = _activePopup._dcrHomes || [];
        var home = null;
        for (var i = 0; i < homes.length; i++) {
            if (homes[i] && homes[i].name === homeName) { home = homes[i]; break; }
        }
        if (!home || !props) return;
        var feat = trailFeatureForHome(props, home);
        setTrailFeatures(feat ? [feat] : []);
    };

    window._dcrShowFactoryFan = function(supplierName) {
        var src = window._dcrMap && window._dcrMap.getSource('hbr-locations');
        if (!src) return;
        // Prefer documented serialize(); fall back to private _data only if
        // serialize is missing on this Mapbox build.
        var data = (src.serialize && src.serialize().data) || src._data;
        if (!data) return;
        var fac = _factoryByName[supplierName];
        if (!fac) return;
        var active = window._dcrMapActiveStatuses || ['Pending', 'Ordered', 'Delivered'];
        var feats = [];
        (data.features || []).forEach(function(f) {
            var homes;
            try { homes = JSON.parse(f.properties.homes_json || '[]'); } catch(_) { return; }
            homes.forEach(function(h) {
                if (h.factory !== supplierName) return;
                if (active.indexOf(h.status) === -1) return;
                var feat = trailFeatureForHome({
                    latitude: f.geometry.coordinates[1],
                    longitude: f.geometry.coordinates[0]
                }, h);
                if (feat) feats.push(feat);
            });
        });
        // Cap at 100 (spec). Order is whatever the source returned — fine for v1.
        setTrailFeatures(feats.slice(0, 100));
    };

    // ========== LEGEND + STATUS FILTER =================================
    var STATUS_LIST = ['Pending', 'Ordered', 'Delivered'];
    var FILTER_KEY = 'dcr-map-status-filter';

    function loadStatusFilter() {
        try {
            var raw = localStorage.getItem(FILTER_KEY);
            if (raw) {
                var v = JSON.parse(raw);
                if (Array.isArray(v)) return v.filter(function(s) { return STATUS_LIST.indexOf(s) !== -1; });
            }
        } catch(_) {}
        return STATUS_LIST.slice();  // default: all on
    }
    function saveStatusFilter(active) {
        try { localStorage.setItem(FILTER_KEY, JSON.stringify(active)); } catch(_) {}
        window._dcrMapActiveStatuses = active.slice();
    }

    function countByStatus(features) {
        var c = { Pending: 0, Ordered: 0, Delivered: 0 };
        features.forEach(function(f) {
            try {
                JSON.parse(f.properties.homes_json || '[]').forEach(function(h) {
                    if (c[h.status] != null) c[h.status]++;
                });
            } catch(_) {}
        });
        return c;
    }

    function buildLegend(map, geojson) {
        var prior = container.querySelector('.dcr-legend');
        if (prior) prior.remove();

        var active = loadStatusFilter();
        window._dcrMapActiveStatuses = active.slice();
        var counts = countByStatus(geojson.features);
        var theme = currentTheme();
        var isBlock = !isMapPage;

        var el = document.createElement('div');
        el.className = 'dcr-legend' + (theme === 'dark' ? ' dcr-legend--dark' : '') + (isBlock ? ' dcr-legend--block' : '');
        var rows = STATUS_LIST.map(function(s) {
            var on = active.indexOf(s) !== -1;
            return '<div class="dcr-legend__row' + (on ? '' : ' is-off') + '" data-status="' + s + '">'
                + '<span class="dcr-legend__swatch dot--' + s.toLowerCase() + '"></span>'
                + '<span>' + s + '</span>'
                + '<span class="dcr-legend__count">' + (counts[s] || 0) + '</span>'
                + (isBlock ? '' : '<input type="checkbox" class="dcr-legend__check" ' + (on ? 'checked' : '') + ' tabindex="-1">')
                + '</div>';
        }).join('');
        var footer = isBlock ? '' :
            '<div class="dcr-legend__footer"><a data-act="all">Show all</a><a data-act="none">Hide all</a></div>';
        el.innerHTML = (isBlock ? '' : '<div class="dcr-legend__title">Deal status</div>') + rows + footer;
        container.appendChild(el);

        if (!isBlock) {
            el.addEventListener('click', function(e) {
                var row = e.target.closest('.dcr-legend__row');
                var act = e.target.getAttribute('data-act');
                if (row) {
                    var s = row.getAttribute('data-status');
                    var idx = active.indexOf(s);
                    if (idx === -1) active.push(s); else active.splice(idx, 1);
                } else if (act === 'all') {
                    active = STATUS_LIST.slice();
                } else if (act === 'none') {
                    active = [];
                } else {
                    return;
                }
                saveStatusFilter(active);
                applyStatusFilter(map);
                buildLegend(map, geojson);  // re-render to refresh checks/counts
            });
        }
    }

    function applyStatusFilter(map) {
        var active = window._dcrMapActiveStatuses || STATUS_LIST.slice();
        if (map.getLayer('unclustered-point')) {
            map.setFilter('unclustered-point',
                ['in', ['get', 'status'], ['literal', active]]);
        }
        // Heatmap stays as-is — it's a coarse density overlay, not status-aware.
    }

    function loadData(map) {
        frappe.call({
            method: 'dcr.api.map.get_heatmap_data',
            callback: function(r) {
                if (!r.message || !r.message.length) return;
                var geojson = {
                    type: 'FeatureCollection',
                    features: r.message.map(function(d) {
                        return {
                            type: 'Feature',
                            geometry: { type: 'Point', coordinates: [d.longitude, d.latitude] },
                            properties: {
                                community_name: d.community_name,
                                address: d.address,
                                space_number: d.space_number || '',
                                city: d.city || '',
                                state: d.state || '',
                                zip: d.zip || '',
                                hbr_count: d.hbr_count,
                                status: d.status || 'Pending',
                                // Stringified so feature-state can survive
                                // through Mapbox; parsed in popup handler.
                                homes_json: JSON.stringify(d.homes || [])
                            }
                        };
                    })
                };

                // Heatmap layer
                map.addSource('hbr-locations', { type: 'geojson', data: geojson });
                map.addLayer({
                    id: 'hbr-heat',
                    type: 'heatmap',
                    source: 'hbr-locations',
                    paint: {
                        'heatmap-weight': ['interpolate', ['linear'], ['get', 'hbr_count'], 1, 0.3, 10, 1],
                        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 12, 3],
                        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 15, 12, 30],
                        'heatmap-opacity': 0.6
                    }
                });

                // Pin layer — one symbol per backend feature, no clustering.
                // Backend aggregates by (coords, address, space_number) into
                // one feature, so each pin = one home or one stacked address.
                //
                // Register all 12 status icons (puck + full × light + dark × 3 statuses).
                // Mapbox needs them in the sprite under a stable name; we pick the
                // theme variant at render time via a `match` expression on `status`.
                var STATUSES = ['pending', 'ordered', 'delivered'];
                var THEMES = ['light', 'dark'];
                var STYLES = ['puck', 'full'];
                var iconLoadCount = 0;
                var ICON_TOTAL = STATUSES.length * THEMES.length * STYLES.length;
                function onIconLoaded() {
                    iconLoadCount++;
                    if (iconLoadCount < ICON_TOTAL) return;
                    _pinsLoaded = true;
                    addHomeLayer();
                }
                saveStatusFilter(loadStatusFilter());  // hydrate global before addHomeLayer
                STATUSES.forEach(function(status) {
                    THEMES.forEach(function(theme) {
                        STYLES.forEach(function(style) {
                            var imgName = 'home-' + style + '-' + theme + '-' + status;
                            var imgUrl = '/assets/dcr/images/' + imgName + '.png';
                            map.loadImage(imgUrl, function(err, img) {
                                if (!err && img && !map.hasImage(imgName)) {
                                    map.addImage(imgName, img);
                                }
                                onIconLoaded();
                            });
                        });
                    });
                });

                function addHomeLayer() {
                    var theme = currentTheme();
                    map.addLayer({
                        id: 'unclustered-point',
                        type: 'symbol',
                        source: 'hbr-locations',
                        minzoom: 6.5,
                        layout: {
                            'icon-image': iconImageExpr(theme, puckFullThreshold),
                            'icon-size': iconSizeExpr(puckFullThreshold),
                            'icon-anchor': iconAnchorExpr(puckFullThreshold),
                            'icon-allow-overlap': true
                        },
                        filter: currentStatusFilter()
                    });
                    // Build legend once the layer exists. setTimeout(0) to
                    // let Mapbox finish the addLayer microtasks before we
                    // call setFilter on it.
                    setTimeout(function() { buildLegend(map, geojson); }, 0);
                }

                map.on('click', 'unclustered-point', function(e) {
                    var f = e.features[0];
                    var props = Object.assign({}, f.properties);
                    var homes;
                    try { homes = JSON.parse(props.homes_json || '[]'); } catch(_) { homes = []; }
                    var lngLat = f.geometry.coordinates;
                    var html, popup;
                    if (homes.length > 1) {
                        html = renderStackedHtml(props, homes);
                        popup = openPopup(map, lngLat, html, { offset: 18 });
                    } else {
                        html = renderSingleHomeHtml(props, homes[0] || {});
                        popup = openPopup(map, lngLat, html, { offset: 18 });
                    }
                    popup._dcrProps = props;
                    popup._dcrHomes = homes;
                });

                // Cursor on hover
                map.on('mouseenter', 'unclustered-point', function() { map.getCanvas().style.cursor = 'pointer'; });
                map.on('mouseleave', 'unclustered-point', function() { map.getCanvas().style.cursor = ''; });
            }
        });
    }

    function loadFactories(map) {
        frappe.call({
            method: 'dcr.api.map.get_factory_locations',
            callback: function(r) {
                if (!r.message || !r.message.length) return;
                var geojson = {
                    type: 'FeatureCollection',
                    features: r.message.map(function(d) {
                        if (window._dcrIndexFactory) window._dcrIndexFactory(d);
                        return {
                            type: 'Feature',
                            geometry: { type: 'Point', coordinates: [d.longitude, d.latitude] },
                            properties: {
                                name: d.name,
                                supplier_name: d.supplier_name,
                                city: d.city || '',
                                pending_count: d.pending_count || 0,
                                ordered_count: d.ordered_count || 0,
                                delivered_count: d.delivered_count || 0,
                                total_12mo: d.total_12mo || 0
                            }
                        };
                    })
                };
                map.addSource('factory-locations', { type: 'geojson', data: geojson });

                // Try to load factory pin assets; fall back to a black circle
                // if either asset is missing (graceful degrade).
                var factoryLight = '/assets/dcr/images/factory-pin-light.png';
                var factoryDark  = '/assets/dcr/images/factory-pin-dark.png';
                var fLoaded = 0, fSuccess = 0;
                function onFactoryIconDone() {
                    fLoaded++;
                    if (fLoaded < 2) return;
                    if (fSuccess === 2) {
                        map.addLayer({
                            id: 'factory-point',
                            type: 'symbol',
                            source: 'factory-locations',
                            layout: {
                                'icon-image': ['case',
                                    ['==', ['literal', currentTheme()], 'dark'],
                                    'factory-pin-dark', 'factory-pin-light'],
                                'icon-size': 0.5,
                                'icon-anchor': 'bottom',
                                'icon-allow-overlap': true
                            }
                        });
                    } else {
                        map.addLayer({
                            id: 'factory-point',
                            type: 'circle',
                            source: 'factory-locations',
                            paint: {
                                'circle-radius': 8,
                                'circle-color': '#000000',
                                'circle-stroke-color': '#ffffff',
                                'circle-stroke-width': 2
                            }
                        });
                    }
                    bindFactoryClick();
                }
                map.loadImage(factoryLight, function(err, img) {
                    if (!err && img) {
                        if (!map.hasImage('factory-pin-light')) map.addImage('factory-pin-light', img);
                        fSuccess++;
                    }
                    onFactoryIconDone();
                });
                map.loadImage(factoryDark, function(err, img) {
                    if (!err && img) {
                        if (!map.hasImage('factory-pin-dark')) map.addImage('factory-pin-dark', img);
                        fSuccess++;
                    }
                    onFactoryIconDone();
                });

                function bindFactoryClick() {
                    map.on('click', 'factory-point', function(e) {
                        var f = e.features[0];
                        var props = Object.assign({}, f.properties);
                        var lngLat = f.geometry.coordinates;
                        var p = openPopup(map, lngLat, renderFactoryHtml(props), { offset: 14 });
                        p._dcrProps = props;
                    });
                    map.on('mouseenter', 'factory-point', function() { map.getCanvas().style.cursor = 'pointer'; });
                    map.on('mouseleave', 'factory-point', function() { map.getCanvas().style.cursor = ''; });
                }
            }
        });
    }

    loadMapbox(initMap);
})();
"""

    # Detect the correct fieldname for JS (differs by Frappe version)
    js_field = None
    for candidate in ("script", "javascript", "js"):
        if frappe.db.has_column("Custom HTML Block", candidate):
            js_field = candidate
            break

    if frappe.db.exists("Custom HTML Block", block_name):
        updates = {"html": html_content}
        if js_field:
            updates[js_field] = js_content
        # IMPORTANT: update_modified must be True (default) so the block's
        # `modified` timestamp bumps. Frappe's desk HTTP cache keys off
        # `modified` — without a bump, browsers get the stale rendered HTML
        # even though the DB row is new.
        frappe.db.set_value("Custom HTML Block", block_name, updates)
        frappe.db.commit()
        # Clear Frappe's in-process doc cache
        frappe.clear_document_cache("Custom HTML Block", block_name)
        # Bust any Workspace that embeds this block — the workspace render
        # is cached by its own `modified`, so we need to touch every workspace
        # referencing this block in its content JSON.
        workspaces = frappe.get_all(
            "Workspace",
            filters={"content": ["like", f"%{block_name}%"]},
            pluck="name",
        )
        for ws in workspaces:
            frappe.db.set_value("Workspace", ws, "modified", frappe.utils.now())
            frappe.clear_document_cache("Workspace", ws)
        frappe.db.commit()
    else:
        new_doc = {
            "doctype": "Custom HTML Block",
            "name": block_name,
            "html": html_content,
            "private": 0,
        }
        if js_field:
            new_doc[js_field] = js_content
        frappe.get_doc(new_doc).insert(ignore_permissions=True)
