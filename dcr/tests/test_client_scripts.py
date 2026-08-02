"""Static regression checks for Frappe client scripts.

There is no JavaScript test harness in this repo, so these tests pin critical
workflow guards in the client scripts.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestDealerPortalClientScript(unittest.TestCase):

    def test_portal_uses_scoped_api_and_review_actions(self):
        script = (ROOT / "dcr/public/js/dealer_portal.js").read_text()
        page = (ROOT / "dcr/www/dealer_portal.html").read_text()
        css = (ROOT / "dcr/public/css/dealer_portal.css").read_text()

        self.assertIn("dcr.api.dealer_portal.", script)
        self.assertIn('api("get_portal_context")', script)
        self.assertIn('api("submit_hbr_for_review"', script)
        self.assertIn('api("save_hbr_draft"', script)
        self.assertIn('data-action="edit-request"', script)
        self.assertIn("upload_document", script)
        self.assertIn('data-csrf-token="{{ csrf_token }}"', page)
        self.assertIn("dealer_portal.css", page)
        self.assertIn("dcr-portal-shell", css)


class TestHomeBuildRequestClientScript(unittest.TestCase):

    def test_cash_deals_do_not_show_create_loan_application_button(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("if (frm.doc.financing_type === 'Floored')", script)
        self.assertNotIn("if (frm.doc.financing_type !== 'Floored') return;", script)

    def test_cash_deals_hide_loan_stage_field(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("update_stage_field_visibility(frm)", script)
        self.assertIn("function update_stage_field_visibility(frm)", script)
        self.assertIn("frm.toggle_display('custom_loan_stage', show_stage)", script)
        self.assertIn("var show_stage = frm.doc.financing_type === 'Floored'", script)
        self.assertNotIn("set_df_property('custom_loan_stage', 'hidden'", script)
        self.assertNotIn("setTimeout(apply, 500)", script)
        self.assertNotIn("setTimeout(apply, 1500)", script)

    def test_delivery_address_search_falls_back_to_url_restricted_browser_token(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("method: 'dcr.api.map.search_address'", script)
        self.assertIn("frm._dcr_address_query", script)
        self.assertIn("function search_address_in_browser(frm, query, callback)", script)
        self.assertIn("method: 'dcr.api.map.get_map_settings'", script)
        self.assertIn("api.mapbox.com/search/geocode/v6/forward", script)
        self.assertIn("function parse_mapbox_address_feature(feature)", script)
        self.assertNotIn("api.mapbox.com/geocoding/v5", script)

    def test_hbr_kanban_is_locked_without_blocking_card_links(self):
        script = (ROOT / "dcr/public/js/hbr_kanban_lock.js").read_text()
        hooks = (ROOT / "dcr/hooks.py").read_text()

        self.assertIn("Sortable.get(element)", script)
        self.assertIn("sortable.option('disabled', true)", script)
        self.assertIn(".add-new-column, .kanban .column-options", script)
        self.assertIn("frappe.router.on('change', watch_route)", script)
        self.assertNotIn("pointer-events: none", script)
        self.assertIn('versioned_asset("/assets/dcr/js/hbr_kanban_lock.js")', hooks)
        self.assertIn("dcr.api.kanban.update_order_for_single_card", hooks)

    def test_cash_deals_keep_lending_connections_hidden_after_async_render(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("frm._dcr_connections_observer = new MutationObserver", script)
        self.assertIn("function connection_wrappers()", script)
        self.assertIn("$(frm.wrapper).find('.form-documents')", script)
        self.assertIn("$card.closest('.col-md-4, .col-sm-6, .col-xs-12')", script)
        self.assertIn("$title.text().trim() !== 'Lending'", script)
        self.assertIn("if (attempts > 30) clearInterval(iv)", script)

    def test_create_loan_application_prefetches_hbr_defaults(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("create_loan_application_from_hbr(frm)", script)
        self.assertIn("function create_loan_application_from_hbr(frm)", script)
        self.assertIn("method: 'dcr.api.lending.get_loan_application_defaults'", script)
        self.assertIn("home_build_request: frm.doc.name", script)
        self.assertIn("frappe.new_doc('Loan Application', Object.assign(defaults, r.message || {}))", script)
        self.assertIn("frappe.new_doc('Loan Application', defaults)", script)

    def test_dashboard_loan_application_plus_uses_prefetch_path(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()
        patch = (
            ROOT / "dcr/public/js/hbr_dashboard_plus_patch_20260525_10.js"
        ).read_text()
        hooks = (ROOT / "dcr/hooks.py").read_text()

        self.assertIn('versioned_asset("/assets/dcr/js/home_build_request.js")', hooks)
        self.assertIn(
            'versioned_asset("/assets/dcr/js/hbr_dashboard_plus_patch_20260525_10.js")',
            hooks,
        )
        self.assertIn("bind_loan_application_connection_create(frm)", script)
        self.assertIn("function bind_loan_application_connection_create(frm)", script)
        self.assertIn("function is_loan_application_connection_click(target)", script)
        self.assertIn("this.addEventListener('click', intercept, true)", script)
        self.assertIn('.document-link[data-doctype="Loan Application"]', script)
        self.assertIn('.document-link:contains("Loan Application")', script)
        self.assertIn("click.dcrLoanApplicationFromHbr", script)
        self.assertIn("e.stopImmediatePropagation()", script)
        self.assertIn("create_loan_application_from_hbr(frm)", script)
        self.assertIn("bind_hbr_loan_application_plus(frm)", patch)
        self.assertIn("this.addEventListener('click', intercept, true)", patch)
        self.assertIn("__dcr_hbr_plus_patch_20260525_10", patch)
        self.assertIn("dcr.api.lending.get_loan_application_defaults", patch)


class TestCustomerClientScript(unittest.TestCase):

    def test_dealer_document_uploads_wait_for_each_save(self):
        script = (ROOT / "dcr/public/js/customer.js").read_text()

        self.assertIn("patch_dealer_document_uploads(frm)", script)
        for fieldname in [
            "dealer_license_copy",
            "sellers_permit_copy",
            "w9_copy",
            "retailer_application_copy",
        ]:
            self.assertIn(f"'{fieldname}'", script)
        self.assertIn("frm.__dcr_dealer_document_save_queue", script)
        self.assertIn("control.on_upload_complete = function(attachment)", script)
        self.assertIn("dcr.api.dealer_documents.set_dealer_document", script)
        self.assertIn("frm.doc.modified = response.message.modified", script)
        self.assertIn("frm.doc.__unsaved = 0", script)
        self.assertIn(
            "removeEventListener('beforeunload', frm.beforeUnloadListener, { capture: true })",
            script,
        )
        self.assertNotIn("await frm.save()", script)
        self.assertNotIn("attach_control.set_value(attachment.file_url)", script)


class TestLoanClientScript(unittest.TestCase):

    def test_loan_form_recalculates_visible_interest_only_totals(self):
        script = (ROOT / "dcr/public/js/loan.js").read_text()

        self.assertIn("function calculate_loan_preview(frm)", script)
        self.assertIn("amount * rate / 1200", script)
        self.assertIn("frm.fields_dict.qualifying_amount", script)
        self.assertIn("? frm.doc.qualifying_amount", script)
        self.assertNotIn("frm.doc.qualifying_amount || frm.doc.loan_amount", script)
        self.assertIn("qualifying_amount: function(frm)", script)
        self.assertIn("function ensure_loan_preview_defaults(frm)", script)
        self.assertIn("frm.set_value('repayment_periods', 12)", script)
        self.assertIn("frm.set_value('qualifying_amount', frm.doc.loan_amount)", script)
        self.assertIn("set_loan_calculated_value(frm, 'monthly_repayment_amount', monthly)", script)
        self.assertIn("set_loan_calculated_value(frm, 'total_payment', total_amount)", script)
        self.assertIn("custom_projected_ltv", script)

    def test_loan_defaults_only_apply_to_fields_on_the_new_loan_form(self):
        script = (ROOT / "dcr/public/js/loan_list_context_patch_20260525_14.js").read_text()

        self.assertIn("cur_frm.fields_dict[field]", script)


class TestPurchaseOrderEmailClientScript(unittest.TestCase):
    def test_purchase_order_preview_hydrates_payment_type_from_hbr(self):
        script = (ROOT / "dcr/public/js/email_preview.js").read_text()
        hooks = (ROOT / "dcr/hooks.py").read_text()

        self.assertIn("frappe.ui.form.on('Purchase Order'", script)
        self.assertIn("function hydrate_payment_type(frm)", script)
        self.assertIn("if (frm.doc.docstatus === 1) return;", script)
        self.assertEqual(script.count("if (frm.doc.docstatus === 1) return;"), 2)
        self.assertIn("r.financing_type === 'Floored' ? 'Flooring' : 'COD'", script)
        self.assertIn("dcr.api.dcr_email.preview_document_email", script)
        self.assertIn("emails.api.send_document_email", script)
        self.assertIn('versioned_asset("/assets/dcr/js/email_preview.js")', hooks)

    def test_disbursement_notice_passes_hbr_not_serial_number(self):
        script = (ROOT / "dcr/public/js/loan.js").read_text()

        self.assertIn("home_build_request: frm.doc.home_build_request || ''", script)
        self.assertNotIn("home_build_request: frm.doc.home_serial_no || ''", script)

    def test_loan_list_create_uses_loan_application_context(self):
        script = (
            ROOT / "dcr/public/js/loan_list_context_patch_20260525_14.js"
        ).read_text()
        hooks = (ROOT / "dcr/hooks.py").read_text()

        self.assertIn(
            'versioned_asset("/assets/dcr/js/loan_list_context_patch_20260525_14.js")',
            hooks,
        )
        self.assertIn("function current_loan_application()", script)
        self.assertIn('new URLSearchParams(window.location.search).get("loan_application")', script)
        self.assertIn('window.location.pathname === "/desk/loan"', script)
        self.assertIn("function is_create_loan_click(target)", script)
        self.assertIn('label === "Add Loan" || label === "Create a new Loan"', script)
        self.assertIn("method: \"dcr.api.lending.get_loan_defaults_from_application\"", script)
        self.assertIn('frappe.new_doc("Loan", defaults)', script)
        self.assertIn("apply_defaults_after_route(defaults, 0)", script)
        self.assertIn('cur_frm.doctype === "Loan"', script)
        self.assertIn("cur_frm.set_value(field, defaults[field])", script)
        self.assertIn("document.addEventListener(\"click\", intercept, true)", script)
        # frappe.ready is a website/portal API, undefined in the desk app —
        # calling it throws "frappe.ready is not a function" on every load.
        # The initial-load bind must use jQuery's ready instead.
        self.assertNotIn("frappe.ready(", script)
        self.assertIn("$(document).ready(bind)", script)


class TestLoanApplicationClientScript(unittest.TestCase):

    def test_loan_application_recalculates_after_async_hydration(self):
        script = (ROOT / "dcr/public/js/loan_application.js").read_text()

        self.assertIn("function refresh_calculations(frm)", script)
        self.assertIn("refresh_calculations(frm);", script)
        self.assertIn("function set_calculated_value(frm, fieldname, value)", script)

    def test_connection_created_new_loan_application_hydrates_from_hbr_onload(self):
        script = (ROOT / "dcr/public/js/loan_application.js").read_text()

        self.assertIn("onload: function(frm)", script)
        self.assertIn("schedule_hbr_hydration(frm)", script)
        self.assertIn("refresh: function(frm)", script)
        self.assertIn("function schedule_hbr_hydration(frm)", script)
        self.assertIn("function hbr_defaults_complete(frm)", script)
        self.assertIn("frm.doc.__hbr_hydration_attempts >= 20", script)
        self.assertIn("setTimeout(function()", script)
        self.assertIn("function hydrate_from_home_build_request(frm)", script)
        self.assertIn("frm.doc.__hbr_hydrating === frm.doc.home_build_request", script)
        self.assertIn("frm.doc.__hbr_hydrated === frm.doc.home_build_request && hbr_defaults_complete(frm)", script)
        self.assertIn("frm.doc.__hbr_hydrated = frm.doc.home_build_request", script)
        self.assertIn("frm.doc.__hbr_hydrating = null", script)
        self.assertIn("method: 'dcr.api.lending.get_loan_application_defaults'", script)
        self.assertIn("apply_loan_application_defaults(frm, r.message || {})", script)
        self.assertIn("frappe.db.get_doc('Home Build Request', frm.doc.home_build_request)", script)
        self.assertIn("apply_hbr_fetch_from_fields(frm, hbr, 'home_build_request')", script)
        self.assertIn("function apply_loan_application_defaults(frm, defaults)", script)
        self.assertIn("function apply_hbr_fetch_from_fields(frm, hbr, link_fieldname)", script)
        self.assertIn("df.fetch_from.indexOf(link_fieldname + '.')", script)
        self.assertIn("set_if_empty(frm, 'applicant', defaults.applicant)", script)
        self.assertIn("set_if_empty(frm, 'loan_amount', defaults.loan_amount)", script)
        self.assertIn("set_if_empty(frm, 'requested_advance_amount', defaults.requested_advance_amount)", script)
        self.assertIn("set_if_empty(frm, 'custom_quote_amount', defaults.custom_quote_amount)", script)
        self.assertIn("set_if_empty(frm, 'buyer_name', defaults.buyer_name)", script)
        self.assertIn("set_if_empty(frm, 'applicant_email_address', defaults.applicant_email_address)", script)
        self.assertIn("set_if_empty(frm, 'applicant_phone_number', defaults.applicant_phone_number)", script)
        self.assertIn("set_if_empty(frm, 'address_line_1', defaults.address_line_1)", script)
        self.assertIn("hydrate_applicant_address(frm, customer && customer.customer_primary_address)", script)
        self.assertIn("if (!frm.fields_dict[fieldname]) return", script)
        self.assertIn("set_if_empty(frm, 'loan_product', defaults.loan_product)", script)
        self.assertIn("set_if_empty(frm, 'rate_of_interest', defaults.rate_of_interest)", script)
        self.assertIn("hydrate_applicant_contact(frm)", script)

    def test_new_loan_application_fetches_required_contact_fields(self):
        script = (ROOT / "dcr/public/js/loan_application.js").read_text()

        self.assertIn("function hydrate_applicant_contact(frm)", script)
        self.assertIn("frm.doc.__contact_fetched_for === frm.doc.applicant", script)
        self.assertIn("['email_id', 'mobile_no', 'customer_primary_address']", script)
        self.assertNotIn("frappe.db.get_value('Customer', frm.doc.applicant, ['email_id', 'mobile_no', 'phone']", script)
        self.assertIn("method: 'frappe.client.get_list'", script)
        self.assertIn("doctype: 'Dynamic Link'", script)
        self.assertIn("link_doctype: 'Customer'", script)
        self.assertIn("frappe.db.get_value('Contact', r.message[0].parent, ['email_id', 'mobile_no']", script)
        self.assertNotIn("frappe.db.get_value('Contact', r.message[0].parent, ['email_id', 'mobile_no', 'phone']", script)
        self.assertIn("set_if_empty(frm, 'applicant_email_address', details.email_id)", script)
        self.assertIn("set_if_empty(frm, 'applicant_phone_number', details.mobile_no)", script)

    def test_hbr_documents_render_does_not_keep_saved_app_dirty(self):
        script = (ROOT / "dcr/public/js/loan_application.js").read_text()

        self.assertIn("if (JSON.stringify(current) === JSON.stringify(target)) return;", script)
        self.assertIn("var was_dirty = frm.is_dirty && frm.is_dirty();", script)
        self.assertIn("if (!was_dirty && !frm.is_new())", script)
        self.assertIn("frm.doc.__unsaved = 0", script)

    def test_submitted_application_refresh_does_not_rewrite_calculated_fields(self):
        script = (ROOT / "dcr/public/js/loan_application.js").read_text()

        self.assertIn("if (frm.doc.docstatus === 0)", script)
        self.assertIn(
            "if (frm.doc.docstatus === 0 && frm.doc.applicant)",
            script,
        )
        self.assertIn("calculate_monthly_interest(frm)", script)
        self.assertIn("calculate_preapproval_fields(frm)", script)


class TestHbrConnectionDefaultsClientScript(unittest.TestCase):

    def test_order_connection_targets_use_shared_hbr_fetch_script(self):
        hooks = (ROOT / "dcr/hooks.py").read_text()
        script = (ROOT / "dcr/public/js/hbr_connection_defaults.js")

        self.assertTrue(script.exists())
        for doctype in ["Purchase Order", "Purchase Invoice", "Purchase Receipt", "Payment Entry", "Signature Request"]:
            self.assertIn(f'"{doctype}": "public/js/hbr_connection_defaults.js"', hooks)

    def test_shared_hbr_fetch_script_applies_customize_form_fetch_from_fields(self):
        script = (ROOT / "dcr/public/js/hbr_connection_defaults.js").read_text()

        self.assertIn('"Purchase Order": "custom_home_build_request"', script)
        self.assertIn('"Purchase Invoice": "home_build_request"', script)
        self.assertIn("frappe.meta.get_docfields(frm.doc.doctype)", script)
        self.assertIn('df.fetch_from.indexOf(link_fieldname + ".")', script)
        self.assertIn("frm.set_value(df.fieldname, hbr[source_field])", script)

    def test_generated_invoice_and_payment_infer_hbr_from_source_documents(self):
        script = (ROOT / "dcr/public/js/hbr_connection_defaults.js").read_text()

        self.assertIn("function infer_purchase_invoice_hbr(frm, link_fieldname)", script)
        self.assertIn('"Purchase Receipt"', script)
        self.assertIn("item.purchase_receipt", script)
        self.assertIn("function infer_payment_entry_hbr(frm, link_fieldname)", script)
        self.assertIn('row.reference_doctype === "Purchase Invoice"', script)
        self.assertIn("return frm.set_value(link_fieldname, hbr)", script)

    def test_payment_outstanding_calculation_does_not_dirty_submitted_docs(self):
        script = (ROOT / "dcr/public/js/hbr_connection_defaults.js").read_text()

        self.assertIn("function recompute_selected_outstanding(frm)", script)
        self.assertIn("if (!frm.fields_dict.custom_total_outstanding) return;", script)
        self.assertIn("if (frm.doc.docstatus === 0)", script)
        self.assertIn("frm.doc.custom_total_outstanding = total", script)
        self.assertIn('frm.refresh_field("custom_total_outstanding")', script)

    def test_signature_request_connection_sets_hbr_reference_doctype(self):
        script = (ROOT / "dcr/public/js/hbr_connection_defaults.js").read_text()

        self.assertIn('frappe.ui.form.on("Signature Request"', script)
        self.assertIn("function set_hbr_reference_doctype(frm)", script)
        self.assertIn("frm.doc.reference_name", script)
        self.assertIn("frm.set_value(\"reference_doctype\", \"Home Build Request\")", script)


class TestLoanDisbursementClientScript(unittest.TestCase):

    def test_connection_created_disbursement_fetches_factory_from_hbr(self):
        script = (ROOT / "dcr/public/js/loan_disbursement.js").read_text()

        self.assertIn("hydrate_from_home_build_request(frm)", script)
        self.assertIn("home_build_request: function(frm)", script)
        self.assertIn("function hydrate_from_home_build_request(frm)", script)
        self.assertIn("frappe.db.get_value('Home Build Request', frm.doc.home_build_request, ['factory'])", script)
        self.assertIn("frm.set_value('factory', r.message.factory)", script)


class TestSidebarFixClientScript(unittest.TestCase):

    def test_workspace_routes_match_boot_keys_or_labels(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("function workspace_from_slug", script)
        self.assertIn("slugify(data.label)", script)
        self.assertIn("workspace_from_slug(route[0])", script)
        self.assertIn("workspace_from_slug(ws_slug)", script)
        self.assertIn("workspace.label", script)
        self.assertNotIn("if (route.length === 1 && route[0]) return route[0].toLowerCase();", script)
        self.assertNotIn("var data = map[slug];", script)

    def test_sidebar_filters_accept_frappe_filter_row_shapes(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("if (Array.isArray(str)) return str;", script)
        self.assertIn("function filter_parts(f)", script)
        self.assertIn("f.length === 3", script)
        self.assertIn("filters_to_route_options(filters)", script)
        self.assertIn('parts.doctype ? parts.doctype + "." + parts.field : parts.field', script)
        self.assertIn("var entry = [parts.operator, parts.value]", script)
        self.assertIn("frappe.route_options = opts", script)
        self.assertIn("e.preventDefault()", script)
        self.assertIn("e.stopImmediatePropagation()", script)
        self.assertIn('frappe.set_route(["List", item.link_to, view])', script)
        self.assertIn("function route_options_from_anchor(anchor, item)", script)

    def test_hbr_refresh_prefers_deals_over_stale_access_hint(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn('"homebuildrequest": "Deals"', script)
        self.assertIn('remember_workspace_for_entity(item.link_to, get_workspace_name(), "sidebar-click")', script)
        self.assertIn("remember_doctype_workspace(item.link_to)", script)
        self.assertIn('var DOCTYPE_MAP_KEY = "sidebar_fix_doctype_workspace"', script)
        self.assertIn("doctype_map[entity] || doctype_map[normalize(entity)]", script)
        self.assertIn("var correct = pick_correct_workspace()", script)
        self.assertIn("original_setup(correct)", script)
        self.assertIn("get_workspace_for_entity(entity, candidates)", script)
        self.assertIn("default_workspace_for_entity(entity, candidates)", script)
        self.assertLess(
            script.index("var doctype_workspace = candidate_label(doctype_map[entity] || doctype_map[normalize(entity)], candidates)"),
            script.index("var entity_workspace = get_workspace_for_entity(entity, candidates)"),
        )
        self.assertLess(
            script.index("var entity_workspace = get_workspace_for_entity(entity, candidates)"),
            script.index('localStorage.getItem("dcr_last_workspace")'),
        )
        self.assertLess(
            script.index("var default_workspace = default_workspace_for_entity(entity, candidates)"),
            script.index('localStorage.getItem("dcr_last_workspace")'),
        )

    def test_workspace_fullbleed_injected_style_keeps_content_padding(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("--dcr-workspace-content-padding: clamp(16px, 1.5vw, 24px)", script)
        self.assertIn("padding-left: var(--dcr-workspace-content-padding, 20px) !important", script)
        self.assertIn("padding-right: var(--dcr-workspace-content-padding, 20px) !important", script)
        self.assertIn("body.dcr-workspace-fullbleed {", script)
        self.assertIn("body.dcr-workspace-fullbleed .main-section", script)
        self.assertIn("body.dcr-workspace-fullbleed .page-body", script)
        self.assertIn("body.dcr-workspace-fullbleed .container.page-body", script)
        self.assertIn("body.dcr-workspace-fullbleed[data-route=", script)
        self.assertIn("Workspaces/Map", script)
        self.assertIn('body.dcr-workspace-fullbleed[data-route=\\"Workspaces/Map\\"] .widget.custom-block-widget-box', script)
        self.assertIn('classList.toggle("dcr-workspace-fullbleed", is_workspace)', script)
        self.assertIn('document.body.classList.toggle("dcr-workspace-home", is_workspace)', script)
        self.assertIn("function is_workspace_page_route(route)", script)
        self.assertNotIn("body[data-route^=\\\"Workspaces/\\\"]", script)
        self.assertNotIn("body:has(.workspace-body)", script)
        self.assertNotIn(".navbar", script)
        self.assertNotIn("margin-left: 0 !important", script)
        self.assertNotIn("margin-right: 0 !important", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .workspace-body,", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .codex-editor", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .ce-block,", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .ce-block__content", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .widget,", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .number-card", script)

    def test_sidebar_setup_survives_missing_workspace_links(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("function patch_typelink_get_path()", script)
        self.assertIn("frappe.ui.sidebar_item.TypeLink", script)
        self.assertIn("return original.call(this)", script)
        self.assertIn("return null", script)

    def test_typelink_guard_applied_before_dom_ready(self):
        # The get_path guard must be installed at script-execution time, not
        # only inside init() (which waits for the sidebar DOM container). On a
        # hard refresh Frappe builds the sidebar during boot, before
        # $(document).ready — so a DOM-gated patch lands too late and the first
        # build aborts into a blank sidebar. Guard against regressing that.
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("function patch_typelink_asap(n)", script)
        # The early bootstrap must run outside (before) the $(document).ready
        # init path so it can win the race against Frappe's boot-time build.
        # Match the actual call (with "(function") so a comment mentioning
        # $(document).ready doesn't skew the position check.
        asap_at = script.index("(function patch_typelink_asap")
        ready_at = script.index("$(document).ready(function")
        self.assertLess(asap_at, ready_at, "early TypeLink patch must precede document.ready init")

    def test_transform_filters_guarded_against_null(self):
        # Frappe v16.19's transform_filters runs Object.entries(filters) with no
        # null guard, so a no-filter DocType sidebar link throws and aborts the
        # whole sidebar build. We patch it to coerce null/undefined to {}.
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("function patch_typelink_transform_filters()", script)
        self.assertIn("proto.transform_filters = function", script)
        self.assertIn("filters === undefined || filters === null", script)
        # Must be installed in the early bootstrap, not only DOM-gated init().
        self.assertIn("patch_typelink_transform_filters();", script)

    def test_diagnostic_logging_is_gated_behind_debug_flag(self):
        # The [DCR sidebar] traces are noisy on every navigation. They must be
        # OFF by default and only fire when DCR_SIDEBAR_DEBUG is flipped on, so
        # the production console stays clean. Guard against regressing to raw
        # console.* calls that always log.
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("function dcr_debug_on()", script)
        self.assertIn('window.DCR_SIDEBAR_DEBUG === true', script)
        self.assertIn('localStorage.getItem("DCR_SIDEBAR_DEBUG")', script)

        # The only console.* calls allowed are inside the gated dbg_* helpers.
        for line in script.splitlines():
            stripped = line.strip()
            if "console." not in stripped:
                continue
            self.assertTrue(
                stripped.startswith("function dbg_"),
                f"ungated console call outside dbg_* helper: {stripped}",
            )


if __name__ == "__main__":
    unittest.main()
