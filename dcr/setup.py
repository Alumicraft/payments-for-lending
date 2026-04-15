import frappe


def after_install():
    """Ensure DCR module definition and required groups exist."""
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

    ensure_heatmap_block()

    frappe.db.commit()


def ensure_heatmap_block():
    """Create or update the workspace heatmap Custom HTML Block."""
    block_name = "HBR Heatmap"

    html_content = """<style>
.mapboxgl-ctrl-bottom-left, .mapboxgl-ctrl-bottom-right { transform: translateY(150%); }
</style>
<div id="dcr-heatmap" style="width:100%; height:calc(100vh - 140px); min-height:400px; border-radius: var(--border-radius-lg); overflow: hidden;"></div>"""

    js_content = r"""
(function() {
    var container = root_element.querySelector('#dcr-heatmap');
    if (!container) return;

    // Full-bleed: target Frappe containers via document (outside shadow DOM)
    var selectors = {
        '.layout-main-section': { padding: '0' },
        '.layout-main-section-wrapper': { width: '100%', padding: '0', margin: '0' },
        '.editor-js-container': { margin: '0' },
        '.codex-editor__redactor': { paddingBottom: '0' },
        '.ce-block__content': { maxWidth: '100%', padding: '0' },
        '.ce-block.col-xs-12': { padding: '0' },
        '.widget.custom-block-widget-box': { padding: '0' }
    };
    for (var sel in selectors) {
        var target = document.querySelector(sel);
        if (target) {
            var styles = selectors[sel];
            for (var prop in styles) target.style[prop] = styles[prop];
        }
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
                var map = new mapboxgl.Map({
                    container: container,
                    style: cfg.map_style_url,
                    center: [cfg.default_longitude, cfg.default_latitude],
                    zoom: cfg.default_zoom
                });
                map.addControl(new mapboxgl.NavigationControl(), 'top-right');

                // Day/night mode + icon swap based on Frappe theme
                var _pinsLoaded = false;
                function syncTheme() {
                    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                    try { map.setConfigProperty('basemap', 'lightPreset', isDark ? 'night' : 'day'); } catch(e) {}
                    if (_pinsLoaded) {
                        var layer = map.getLayer('unclustered-point');
                        if (layer) {
                            map.setLayoutProperty('unclustered-point', 'icon-image', isDark ? 'house-pin-dark' : 'house-pin-light');
                        }
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

                // Cluster source
                map.addSource('hbr-clusters', {
                    type: 'geojson',
                    data: geojson,
                    cluster: true,
                    clusterMaxZoom: 14,
                    clusterRadius: 50,
                    clusterProperties: {
                        total_count: ['+', ['get', 'hbr_count']]
                    }
                });

                // Cluster circles
                map.addLayer({
                    id: 'clusters',
                    type: 'circle',
                    source: 'hbr-clusters',
                    filter: ['has', 'point_count'],
                    paint: {
                        'circle-color': '#007AFF',
                        'circle-radius': ['step', ['get', 'total_count'], 20, 5, 26, 15, 34],
                        'circle-stroke-width': 3,
                        'circle-stroke-color': '#fff'
                    }
                });

                // Cluster count labels
                map.addLayer({
                    id: 'cluster-count',
                    type: 'symbol',
                    source: 'hbr-clusters',
                    filter: ['has', 'point_count'],
                    layout: {
                        'text-field': ['to-string', ['get', 'total_count']],
                        'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
                        'text-size': 13
                    },
                    paint: {
                        'text-color': '#ffffff'
                    }
                });

                // Individual points — load both light/dark house markers
                var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                var loaded = 0;
                function onPinLoaded() {
                    loaded++;
                    if (loaded < 2) return;
                    _pinsLoaded = true;
                    map.addLayer({
                        id: 'unclustered-point',
                        type: 'symbol',
                        source: 'hbr-clusters',
                        filter: ['!', ['has', 'point_count']],
                        layout: {
                            'icon-image': isDark ? 'house-pin-dark' : 'house-pin-light',
                            'icon-size': 0.35,
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

                // Zoom into cluster on click
                map.on('click', 'clusters', function(e) {
                    map.getSource('hbr-clusters').getClusterExpansionZoom(
                        e.features[0].properties.cluster_id,
                        function(err, zoom) {
                            if (err) return;
                            map.easeTo({ center: e.features[0].geometry.coordinates, zoom: zoom });
                        }
                    );
                });

                // Cursor styles
                map.on('mouseenter', 'clusters', function() { map.getCanvas().style.cursor = 'pointer'; });
                map.on('mouseleave', 'clusters', function() { map.getCanvas().style.cursor = ''; });
                map.on('mouseenter', 'unclustered-point', function() { map.getCanvas().style.cursor = 'pointer'; });
                map.on('mouseleave', 'unclustered-point', function() { map.getCanvas().style.cursor = ''; });
            }
        });
    }

    loadMapbox(initMap);
})();
"""

    if frappe.db.exists("Custom HTML Block", block_name):
        block = frappe.get_doc("Custom HTML Block", block_name)
        block.html = html_content
        block.javascript = js_content
        block.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Custom HTML Block",
            "name": block_name,
            "html": html_content,
            "javascript": js_content,
            "private": 0,
        }).insert(ignore_permissions=True)
