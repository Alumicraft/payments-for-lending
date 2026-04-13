// Fix Frappe sidebar_header.js bug: renderer reads item.icon_url
// but the Desktop Icon DocType field is logo_url.
// Also clear icon so the renderer takes the <img> path for custom images.
// Deferred to after boot data is available.
$(document).on('startup', function() {
    if (frappe.boot && frappe.boot.desktop_icons) {
        frappe.boot.desktop_icons.forEach(function(item) {
            if (item.logo_url && !item.icon_url) {
                item.icon_url = item.logo_url;
            }
            if (item.icon_url && item.icon) {
                item.icon = null;
            }
        });
    }
});
