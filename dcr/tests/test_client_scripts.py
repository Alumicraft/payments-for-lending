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


class TestLoanClientScript(unittest.TestCase):

    def test_disbursement_notice_passes_hbr_not_serial_number(self):
        script = (ROOT / "dcr/public/js/loan.js").read_text()

        self.assertIn("home_build_request: frm.doc.home_build_request || ''", script)
        self.assertNotIn("home_build_request: frm.doc.home_serial_no || ''", script)


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
        self.assertIn("function scrub_fieldname(field)", script)
        self.assertIn("filters_to_route_options(filters)", script)
        self.assertIn("frappe.route_options = opts", script)

    def test_hbr_refresh_prefers_deals_over_stale_access_hint(self):
        script = (ROOT / "dcr/public/js/sidebar_fix.js").read_text()

        self.assertIn('"homebuildrequest": "Deals"', script)
        self.assertIn('remember_workspace_for_entity(item.link_to, get_workspace_name(), "sidebar-click")', script)
        self.assertIn("get_workspace_for_entity(entity, candidates)", script)
        self.assertIn("default_workspace_for_entity(entity, candidates)", script)
        self.assertLess(
            script.index("var entity_workspace = get_workspace_for_entity(entity, candidates)"),
            script.index('localStorage.getItem("dcr_last_workspace")'),
        )
        self.assertLess(
            script.index("var default_workspace = default_workspace_for_entity(entity, candidates)"),
            script.index('localStorage.getItem("dcr_last_workspace")'),
        )


if __name__ == "__main__":
    unittest.main()
