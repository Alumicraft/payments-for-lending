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

    frappe.db.commit()


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
</style>
<div id="dcr-map" style="width:100%; overflow: hidden;"></div>"""

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
                var map = new mapboxgl.Map({
                    container: container,
                    style: cfg.map_style_url,
                    center: [cfg.default_longitude, cfg.default_latitude],
                    zoom: cfg.default_zoom
                });
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
                            zoom: cfg.default_zoom,
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
                            isDark ? 'house-pin-dark' : 'house-pin-light'
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
                }
                map.on('style.load', syncTheme);

                // Watch for Frappe theme changes
                var themeObserver = new MutationObserver(syncTheme);
                themeObserver.observe(document.documentElement, {
                    attributes: true, attributeFilter: ['data-theme']
                });

                map.on('load', function() { loadData(map); });
            }
        });
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
                                hbr_count: d.hbr_count
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
                // Backend already aggregates by address into a single feature
                // with hbr_count, so each pin = one address.
                var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                var loaded = 0;
                function onPinLoaded() {
                    loaded++;
                    if (loaded < 2) return;
                    _pinsLoaded = true;

                    map.addLayer({
                        id: 'unclustered-point',
                        type: 'symbol',
                        source: 'hbr-locations',
                        minzoom: 6.5,
                        layout: {
                            'icon-image': isDark ? 'house-pin-dark' : 'house-pin-light',
                            'icon-size': 0.212,
                            'icon-anchor': 'bottom',
                            'icon-allow-overlap': true
                        }
                    });
                }
                map.loadImage('/assets/dcr/images/map-pin-light.png', function(err, img) {
                    if (!err) map.addImage('house-pin-light', img);
                    onPinLoaded();
                });
                map.loadImage('/assets/dcr/images/map-pin-dark.png', function(err, img) {
                    if (!err) map.addImage('house-pin-dark', img);
                    onPinLoaded();
                });

                // Popup on click - individual points
                map.on('click', 'unclustered-point', function(e) {
                    var p = e.features[0].properties;
                    var html = '<div style="font-family:Inter,sans-serif;font-size:13px;">'
                        + '<strong>' + (p.community_name || 'Unknown') + '</strong><br>'
                        + '<span style="color:#666;">' + (p.address || '') + '</span><br>'
                        + '<span style="font-weight:600;">' + p.hbr_count + ' deal' + (p.hbr_count > 1 ? 's' : '') + '</span><br>'
                        + '<a href="/app/home-build-request?delivery_address=' + encodeURIComponent(p.address) + '" style="color:#2490ef;">View deals</a>'
                        + '</div>';
                    new mapboxgl.Popup({ offset: 15 })
                        .setLngLat(e.features[0].geometry.coordinates)
                        .setHTML(html)
                        .addTo(map);
                });

                // Cursor on hover
                map.on('mouseenter', 'unclustered-point', function() { map.getCanvas().style.cursor = 'pointer'; });
                map.on('mouseleave', 'unclustered-point', function() { map.getCanvas().style.cursor = ''; });
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
