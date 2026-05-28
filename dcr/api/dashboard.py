"""Dashboard chart data methods for DCR workspaces.

Each whitelisted method returns chart data in frappe-charts format:
    {"labels": [...], "datasets": [{"name": ..., "values": [...]}]}

Wiring: each chart is a Dashboard Chart (chart_type="Custom") whose `source`
names a Dashboard Chart Source record. That source's .js config
(dcr/dcr/dashboard_chart_source/<name>/<name>.js) points at one of the methods
below; Frappe's chart widget calls it client-side, passing framework kwargs
(chart_name, filters, timespan, ...) that these methods ignore.

Why custom methods (not built-in Count/Sum charts):
  - Inflows vs Outflows needs two datasets from two different doctypes
  - Past-Due Aging needs CASE WHEN bucketing — not available in the UI form
  - New Deals by Type needs a stacked time-series, which Frappe v16's
    Dashboard Chart UI doesn't render reliably
"""

import frappe
from frappe.utils import add_months, get_first_day, getdate, nowdate


@frappe.whitelist()
def inflows_vs_outflows(**kwargs):
    """Grouped monthly bars: principal advanced vs payments received, last 12 months.

    Outflows source: Loan Disbursement.disbursed_amount, by posting_date month.
    Inflows source:  Loan Repayment.amount_paid, by posting_date month.

    Scope: floored deals only. Loan Disbursement is inherently floor-plan in DCR
    (cash deals don't generate disbursements through DCR's books), so no extra
    filter is applied. If cash deals ever generate Loan records, revisit this.
    """
    labels, keys = _trailing_months()

    outflows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(posting_date, '%%Y-%%m-01') AS m,
               COALESCE(SUM(disbursed_amount), 0) AS total
        FROM `tabLoan Disbursement`
        WHERE docstatus = 1 AND posting_date >= %s
        GROUP BY m
        """,
        (keys[0],),
        as_dict=True,
    )
    inflows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(posting_date, '%%Y-%%m-01') AS m,
               COALESCE(SUM(amount_paid), 0) AS total
        FROM `tabLoan Repayment`
        WHERE docstatus = 1 AND posting_date >= %s
        GROUP BY m
        """,
        (keys[0],),
        as_dict=True,
    )

    return {
        "labels": labels,
        "datasets": [
            {"name": "Principal Advanced", "values": _project({r.m: r.total for r in outflows}, keys)},
            {"name": "Payments Received", "values": _project({r.m: r.total for r in inflows}, keys)},
        ],
    }


@frappe.whitelist()
def past_due_aging(**kwargs):
    """Bucketed past-due dollars from submitted Loan Demands.

    Loan Demand is ERPNext Lending's canonical record for raised demands and
    their unpaid balances. The doctype stores `outstanding_amount` directly
    (= demand_amount - paid_amount - waived_amount), so we sum that rather
    than recomputing — waived amounts shouldn't count as past-due.

    A demand is past-due when demand_date < today and outstanding_amount > 0.

    Granularity: demand-level (one Loan Demand row → one bucket). A loan with
    three unpaid demands shows up in three buckets, which is the right read for
    an accounting workspace (total past-due dollars and their aging).

    Buckets: 1-30, 31-60, 61-90, 90+ days past demand_date.
    """
    buckets = ["1-30", "31-60", "61-90", "90+"]

    rows = frappe.db.sql(
        """
        SELECT
            CASE
                WHEN DATEDIFF(%(today)s, demand_date) BETWEEN 1 AND 30 THEN '1-30'
                WHEN DATEDIFF(%(today)s, demand_date) BETWEEN 31 AND 60 THEN '31-60'
                WHEN DATEDIFF(%(today)s, demand_date) BETWEEN 61 AND 90 THEN '61-90'
                ELSE '90+'
            END AS bucket,
            COALESCE(SUM(outstanding_amount), 0) AS total
        FROM `tabLoan Demand`
        WHERE docstatus = 1
          AND demand_date < %(today)s
          AND outstanding_amount > 0
        GROUP BY bucket
        """,
        {"today": nowdate()},
        as_dict=True,
    )

    return {
        "labels": buckets,
        "datasets": [
            {"name": "Past-Due Amount", "values": _project({r.bucket: r.total for r in rows}, buckets)}
        ],
    }


@frappe.whitelist()
def new_deals_by_type(**kwargs):
    """Monthly Home Build Request counts, stacked by financing_type.

    Last 12 months, two datasets: Cash and Floored. Stacking is enabled on the
    Dashboard Chart record via custom_options (not in this method).
    """
    labels, keys = _trailing_months()

    rows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(creation, '%%Y-%%m-01') AS m,
               financing_type,
               COUNT(*) AS n
        FROM `tabHome Build Request`
        WHERE docstatus = 1 AND creation >= %s
        GROUP BY m, financing_type
        """,
        (keys[0],),
        as_dict=True,
    )

    by_type = {"Cash": {}, "Floored": {}}
    for r in rows:
        if r.financing_type in by_type:
            by_type[r.financing_type][r.m] = r.n

    return {
        "labels": labels,
        "datasets": [
            {"name": "Cash", "values": _project(by_type["Cash"], keys)},
            {"name": "Floored", "values": _project(by_type["Floored"], keys)},
        ],
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _trailing_months(n=12):
    """Return (labels, keys) for the trailing n months, oldest first.

    labels — display strings like "Jun 25".
    keys   — "YYYY-MM-01" strings that MUST match the SQL DATE_FORMAT(date,
             '%Y-%m-01') used in the queries above. Used both to align grouped
             rows onto a gap-free month axis and as the inclusive lower bound
             (keys[0]) for each query's date filter.
    """
    today = getdate(nowdate())
    months = [get_first_day(add_months(today, -i)) for i in range(n - 1, -1, -1)]
    return [m.strftime("%b %y") for m in months], [m.strftime("%Y-%m-01") for m in months]


def _project(values_by_key, keys):
    """Map {key: value} onto an ordered key list, filling 0 for missing keys.

    Aligns grouped SQL aggregates onto a fixed axis (months or aging buckets)
    so the chart renders empty slots instead of skipping them.
    """
    return [values_by_key.get(k, 0) for k in keys]
