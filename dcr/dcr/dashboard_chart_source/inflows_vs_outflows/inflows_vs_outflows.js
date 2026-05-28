frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Inflows vs Outflows"] = {
	method: "dcr.api.dashboard.inflows_vs_outflows",
	filters: [],
};
