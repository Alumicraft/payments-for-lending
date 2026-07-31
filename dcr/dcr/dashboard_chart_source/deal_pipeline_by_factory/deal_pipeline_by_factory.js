frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Deal Pipeline by Factory"] = {
	method: "dcr.api.dashboard.deal_pipeline_by_factory",
	filters: [],
};
