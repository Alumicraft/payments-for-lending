/* DCR Map warm-up.
 *
 * Loaded via app_include_js so it runs on every desk page. Goal: by the
 * time the user navigates to the Map workspace, all expensive prerequisites
 * (Mapbox CDN handshake, GL JS script and pin icons) are
 * already in flight or cached. Deal data is fetched when the map loads,
 * so documents saved after Desk boot appear on the map.
 *
 * Idempotent — guarded by window._dcrMapWarmedUp so multiple route changes
 * don't re-fire the warm-up.
 */
(function () {
  if (typeof window === "undefined") return;
  if (window._dcrMapWarmedUp) return;
  window._dcrMapWarmedUp = true;

  // ---- 1) Preconnect to Mapbox CDN -----------------------------------
  ["https://api.mapbox.com", "https://events.mapbox.com"].forEach(function (
    href
  ) {
    var l = document.createElement("link");
    l.rel = "preconnect";
    l.href = href;
    l.crossOrigin = "anonymous";
    document.head.appendChild(l);
  });

  // ---- 2) Preload the 14 pin icon PNGs --------------------------------
  // Browser starts fetching during HTML parse, parallel with mapbox-gl.js.
  // By the time map.loadImage runs, they're in disk cache.
  var iconNames = [];
  ["pending", "ordered", "delivered"].forEach(function (s) {
    ["light", "dark"].forEach(function (t) {
      ["puck", "full"].forEach(function (style) {
        iconNames.push("home-" + style + "-" + t + "-" + s + ".png");
      });
    });
  });
  iconNames.push("factory-pin-light.png", "factory-pin-dark.png");
  iconNames.forEach(function (name) {
    var l = document.createElement("link");
    l.rel = "preload";
    l.as = "image";
    l.href = "/assets/dcr/images/" + name;
    document.head.appendChild(l);
  });

  // ---- 3) Lazy-load Mapbox GL JS + CSS --------------------------------
  // The map block's loadMapbox() checks for window.mapboxgl before
  // injecting its own script tag — if the warmup got there first, it
  // reuses the global. Defer + async so this never blocks the desk paint.
  var MAPBOX_VER = "v3.3.0";
  if (!window.mapboxgl) {
    var script = document.createElement("script");
    script.src =
      "https://api.mapbox.com/mapbox-gl-js/" + MAPBOX_VER + "/mapbox-gl.js";
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
  }
  if (!document.querySelector('link[href*="mapbox-gl.css"]')) {
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href =
      "https://api.mapbox.com/mapbox-gl-js/" + MAPBOX_VER + "/mapbox-gl.css";
    document.head.appendChild(css);
  }

})();
