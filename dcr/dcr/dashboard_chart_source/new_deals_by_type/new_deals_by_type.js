frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["New Deals by Type"] = {
	method: "dcr.api.dashboard.new_deals_by_type",
	filters: [],
};
