frappe.ready(function () {
    // Saving uses Frappe's native Web Form accept endpoint. Its DCR adapter
    // applies the same scoped service used by the dealer dashboard.
    frappe.web_form.handle_success = function (saved) {
        window.location.assign("/portal?request=" + encodeURIComponent(saved.name));
    };
    frappe.web_form.get_discard_url = function () { return "/portal"; };
});
