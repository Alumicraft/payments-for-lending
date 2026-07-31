frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Repayment Breakdown"] = {
	method: "dcr.api.dashboard.repayment_breakdown",
	filters: [],
};
