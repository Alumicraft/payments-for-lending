// Temporary cache-busting patch for Frappe Cloud asset stores that retain
// stale doctype JS at /assets/dcr/js/home_build_request.js.
(function() {
    if (!window.frappe || !frappe.ui || !frappe.ui.form) return;

    frappe.ui.form.on('Home Build Request', {
        refresh: function(frm) {
            bind_hbr_loan_application_plus(frm);
        }
    });

    function build_defaults(frm) {
        return {
            applicant_type: 'Customer',
            applicant: frm.doc.customer || '',
            loan_product: 'Standard',
            loan_amount: frm.doc.quote_amount || 0,
            requested_advance_amount: frm.doc.quote_amount || 0,
            home_build_request: frm.doc.name,
            home_serial_no: frm.doc.serial_number || '',
            factory: frm.doc.factory || '',
            floor_plan: frm.doc.model_name || '',
            custom_quote_amount: frm.doc.quote_amount || 0
        };
    }

    function create_loan_application_from_hbr(frm) {
        var defaults = build_defaults(frm);
        frappe.call({
            method: 'dcr.api.lending.get_loan_application_defaults',
            args: { home_build_request: frm.doc.name },
            callback: function(r) {
                frappe.new_doc('Loan Application', Object.assign(defaults, r.message || {}));
            },
            error: function() {
                frappe.new_doc('Loan Application', defaults);
            }
        });
    }

    function is_loan_application_plus(target) {
        if (!target || !target.closest) return false;

        var button = target.closest('button, .btn-new, .document-link-badge');
        if (!button) return false;

        var card = button.closest(
            '.document-link, .document-link-badge, .link-item, ' +
            '.col-md-4, .col-sm-6, .col-xs-12'
        );
        if (!card) return false;

        var doctype = card.getAttribute('data-doctype') || $(card).data('doctype');
        if (doctype) return doctype === 'Loan Application';

        return $(card).text().trim().indexOf('Loan Application') !== -1;
    }

    function bind_hbr_loan_application_plus(frm) {
        if (frm.doc.docstatus !== 1 || frm.doc.financing_type !== 'Floored') return;

        function intercept(e) {
            if (!is_loan_application_plus(e.target)) return;

            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            create_loan_application_from_hbr(frm);
            return false;
        }

        function connection_wrappers() {
            var wrappers = $();
            if (frm.dashboard && frm.dashboard.wrapper) {
                wrappers = wrappers.add(frm.dashboard.wrapper);
            }
            if (frm.wrapper) {
                wrappers = wrappers.add($(frm.wrapper).find('.form-documents'));
            }
            wrappers = wrappers.add($('.form-documents'));
            return wrappers;
        }

        function bind() {
            connection_wrappers().each(function() {
                if (this.__dcr_hbr_plus_patch_20260525_10) return;
                this.__dcr_hbr_plus_patch_20260525_10 = true;
                this.addEventListener('click', intercept, true);
            });
        }

        var attempts = 0;
        var iv = setInterval(function() {
            attempts += 1;
            bind();
            if (attempts > 30) clearInterval(iv);
        }, 300);
        bind();

        var wrapper = connection_wrappers().get(0);
        if (wrapper && window.MutationObserver && !frm._dcr_hbr_plus_patch_observer) {
            frm._dcr_hbr_plus_patch_observer = new MutationObserver(bind);
            frm._dcr_hbr_plus_patch_observer.observe(wrapper, { childList: true, subtree: true });
        }
    }
})();
