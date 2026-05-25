(function() {
    "use strict";

    var PATCH_MARKER = "__dcr_loan_list_context_patch_20260525_11";

    function current_loan_application() {
        var route_options = frappe.route_options || {};
        if (route_options.loan_application) return route_options.loan_application;

        try {
            return new URLSearchParams(window.location.search).get("loan_application");
        } catch (e) {
            return null;
        }
    }

    function on_loan_list_route() {
        var route = frappe.get_route ? frappe.get_route() : [];
        if (route[0] === "List" && route[1] === "Loan") return true;
        return window.location.pathname.indexOf("/desk/loan/view/list") !== -1;
    }

    function create_loan_from_application(loan_application) {
        frappe.call({
            method: "dcr.api.lending.get_loan_defaults_from_application",
            args: { loan_application: loan_application },
            freeze: true,
            freeze_message: __("Loading loan details..."),
            callback: function(r) {
                frappe.new_doc("Loan", r.message || {});
            }
        });
    }

    function is_create_loan_click(target) {
        var button = $(target).closest("button, .btn, a")[0];
        if (!button) return false;

        var label = (button.innerText || button.textContent || "").trim();
        return label === "Add Loan" || label === "Create a new Loan";
    }

    function intercept(e) {
        if (!on_loan_list_route()) return;

        var loan_application = current_loan_application();
        if (!loan_application) return;
        if (!is_create_loan_click(e.target)) return;

        e.preventDefault();
        e.stopPropagation();
        if (e.stopImmediatePropagation) e.stopImmediatePropagation();
        create_loan_from_application(loan_application);
    }

    function bind() {
        if (document[PATCH_MARKER]) return;
        document[PATCH_MARKER] = true;
        document.addEventListener("click", intercept, true);
    }

    if (frappe && frappe.router && frappe.router.on) {
        frappe.router.on("change", bind);
    }
    $(document).on("page-change", bind);
    frappe.ready(bind);
})();
