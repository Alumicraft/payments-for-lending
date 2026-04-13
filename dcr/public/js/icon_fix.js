// Intercept frappe.desktop_icons assignment to merge image data from
// boot before the desktop template renders. This prevents the flash
// of letter squares that the post-render DOM patch caused.
(function () {
	var _desktop_icons;
	Object.defineProperty(frappe, "desktop_icons", {
		get: function () { return _desktop_icons; },
		set: function (val) {
			if (Array.isArray(val) && frappe.boot && frappe.boot.desktop_icons) {
				var boot_map = {};
				frappe.boot.desktop_icons.forEach(function (i) {
					if (i.logo_url || i.icon_image) boot_map[i.label] = i;
				});
				val.forEach(function (item) {
					var boot = boot_map[item.label];
					if (boot) {
						if (!item.logo_url) item.logo_url = boot.logo_url;
						if (!item.icon_image) item.icon_image = boot.icon_image;
					}
				});
			}
			_desktop_icons = val;
		},
		configurable: true,
	});

	// Guard against null link_to crashing frappe.router.slug in get_route.
	// Broken workspace sidebar items with null link_to cause TypeError
	// that kills the entire desktop page.
	var _origSlug = frappe.router && frappe.router.slug;
	if (_origSlug) {
		frappe.router.slug = function (name) {
			if (name == null) return "";
			return _origSlug.call(this, name);
		};
	} else {
		// router not loaded yet, patch when ready
		$(document).on("startup", function () {
			if (frappe.router && frappe.router.slug) {
				var orig = frappe.router.slug;
				frappe.router.slug = function (name) {
					if (name == null) return "";
					return orig.call(this, name);
				};
			}
		});
	}
})();
