// Patch desktop icons that have custom images in boot data but render
// as letter squares due to stale layout cache missing logo_url/icon_image.
$(document).on("page-change", function () {
	if (frappe.get_route_str() !== "") return;
	// Desktop page — wait for icons to render, then patch
	setTimeout(function () {
		var boot_icons = frappe.boot.desktop_icons || [];
		document.querySelectorAll(".desktop-icon").forEach(function (el) {
			var label = el.getAttribute("data-id");
			var boot_icon = boot_icons.find(function (i) { return i.label === label; });
			var url = boot_icon && (boot_icon.logo_url || boot_icon.icon_image);
			if (url && !el.getAttribute("data-logo")) {
				var container = el.querySelector(".icon-container");
				if (container) {
					container.innerHTML = '<img class="app-icon" src="' + url + '" alt="' + label + '" />';
					el.setAttribute("data-logo", url);
				}
			}
		});
	}, 300);
});
