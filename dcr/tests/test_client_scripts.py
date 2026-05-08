"""Static regression checks for Frappe client scripts.

There is no JavaScript test harness in this repo, so these tests pin critical
workflow guards in the client scripts.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestHomeBuildRequestClientScript(unittest.TestCase):

    def test_cash_deals_do_not_show_create_loan_application_button(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("if (frm.doc.financing_type === 'Floored')", script)
        self.assertNotIn("if (frm.doc.financing_type !== 'Floored') return;", script)

    def test_cash_deals_hide_loan_stage_field(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("update_stage_field_visibility(frm)", script)
        self.assertIn("function update_stage_field_visibility(frm)", script)
        self.assertIn("frm.toggle_display('custom_loan_stage', !is_cash)", script)
        self.assertIn("frm.toggle_reqd('custom_loan_stage', !is_cash)", script)
        self.assertIn("frm.set_df_property('custom_loan_stage', 'hidden', is_cash ? 1 : 0)", script)
        self.assertIn("var is_cash = frm.doc.financing_type === 'Cash'", script)

    def test_cash_deals_keep_lending_connections_hidden_after_async_render(self):
        script = (ROOT / "dcr/public/js/home_build_request.js").read_text()

        self.assertIn("frm._dcr_connections_observer = new MutationObserver", script)
        self.assertIn("function connection_wrappers()", script)
        self.assertIn("$(frm.wrapper).find('.form-documents')", script)
        self.assertIn("$card.closest('.col-md-4, .col-sm-6, .col-xs-12')", script)
        self.assertIn("$title.text().trim() !== 'Lending'", script)
        self.assertIn("if (attempts > 30) clearInterval(iv)", script)


class TestLoanClientScript(unittest.TestCase):

    def test_disbursement_notice_passes_hbr_not_serial_number(self):
        script = (ROOT / "dcr/public/js/loan.js").read_text()

        self.assertIn("home_build_request: frm.doc.home_build_request || ''", script)
        self.assertNotIn("home_build_request: frm.doc.home_serial_no || ''", script)


class TestLoanApplicationClientScript(unittest.TestCase):

    def test_connection_created_new_loan_application_hydrates_from_hbr_onload(self):
        script = (ROOT / "dcr/public/js/loan_application.js").read_text()

        self.assertIn("onload: function(frm)", script)
        self.assertIn("hydrate_from_home_build_request(frm)", script)
        self.assertIn("function hydrate_from_home_build_request(frm)", script)
        self.assertIn("frm.doc.__hbr_hydrated === frm.doc.home_build_request", script)
        self.assertIn("frm.doc.__hbr_hydrated = frm.doc.home_build_request", script)
        self.assertIn("frappe.db.get_doc('Home Build Request', frm.doc.home_build_request)", script)
        self.assertIn("apply_hbr_fetch_from_fields(frm, hbr, 'home_build_request')", script)
        self.assertIn("function apply_hbr_fetch_from_fields(frm, hbr, link_fieldname)", script)
        self.assertIn("df.fetch_from.indexOf(link_fieldname + '.')", script)
        self.assertIn("set_if_empty(frm, 'applicant', hbr.customer)", script)
        self.assertIn("set_if_empty(frm, 'loan_amount', hbr.home_invoice_plus_freight)", script)
        self.assertIn("set_if_empty(frm, 'buyer_name', hbr.home_buyer)", script)


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

    def test_workspace_fullbleed_injected_style_is_scoped_to_map(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn("body.dcr-workspace-fullbleed[data-route=", script)
        self.assertIn("Workspaces/Map", script)
        self.assertIn('body.dcr-workspace-fullbleed[data-route=\\"Workspaces/Map\\"] .widget.custom-block-widget-box', script)
        self.assertIn('route_key === "workspaces/map"', script)
        self.assertIn('body_route === "workspaces/map"', script)
        self.assertIn('classList.toggle("dcr-workspace-fullbleed", is_map_workspace)', script)
        self.assertNotIn("--dcr-workspace-content-padding", script)
        self.assertNotIn("padding-left: var(--dcr-workspace-content-padding, 20px) !important", script)
        self.assertNotIn("padding-right: var(--dcr-workspace-content-padding, 20px) !important", script)
        self.assertNotIn("body.dcr-workspace-fullbleed {", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .main-section", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .page-body", script)
        self.assertNotIn("body.dcr-workspace-fullbleed .container.page-body", script)
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


if __name__ == "__main__":
    unittest.main()
