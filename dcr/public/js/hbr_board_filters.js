/* Use Frappe's native filter controls on the operational HBR board. */
(function () {
    function show_filters(list) {
        if (!list || list.doctype !== "Home Build Request" || list.view_name !== "Kanban" ||
                !list.filter_area || !list.page || !list.$filter_section || list.__dcr_board_filters) return;
        list.__dcr_board_filters = true;
        list.hide_page_form = false;
        list.page.page_form.show();
        list.$filter_section.appendTo(list.page.page_form);
        // Native metadata determines fields, permissions, link queries and
        // Data-field LIKE matching. Keep the existing filters and board data.
        return Promise.resolve().then(function () { return list.filter_area.make_standard_filters(); }).catch(function () {
            list.__dcr_board_filters = "failed";
            if (typeof frappe !== "undefined" && frappe.show_alert) {
                frappe.show_alert({ message: __("Board filters could not load. Reload the page to try again."), indicator: "red" });
            }
        });
    }
    if (typeof module !== "undefined" && module.exports) module.exports = show_filters;
    if (typeof window !== "undefined") window.dcrShowHbrBoardFilters = show_filters;
})();
