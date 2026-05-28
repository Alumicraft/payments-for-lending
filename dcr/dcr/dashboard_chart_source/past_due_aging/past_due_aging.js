frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Past-Due Aging"] = {
	method: "dcr.api.dashboard.past_due_aging",
	filters: [],
};
