"""Dashboard chart data methods for DCR workspaces.

Each whitelisted method returns chart data in frappe-charts format:
    {"labels": [...], "datasets": [{"name": ..., "values": [...]}]}

These methods are wired to Dashboard Chart records with chart_type = "Custom"
and source = "dcr.api.dashboard.<method_name>".

Why custom methods (not built-in Count/Sum charts):
  - Inflows vs Outflows needs two datasets from two different doctypes
  - Past-Due Aging needs CASE WHEN bucketing — not available in the UI form
  - New Deals by Type needs a stacked time-series, which Frappe v16's
    Dashboard Chart UI doesn't render reliably when combining time-series + group by
"""

import frappe
from frappe.utils import add_months, get_first_day, getdate, nowdate


# --------------------------------------------------------------------------- #
# Chart 1: Inflows vs Outflows — Monthly (Accounting workspace, full-width)
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def inflows_vs_outflows():
    """Grouped monthly bars: principal advanced vs payments received, last 12 months.

    Outflows source: Loan Disbursement.disbursed_amount, grouped by posting_date month.
    Inflows source:  Loan Repayment.amount_paid, grouped by posting_date month.

    Scope: floored deals only. Loan Disbursement is inherently floor-plan in DCR
    (cash deals don't generate disbursements through DCR's books), so no extra
    filter is applied. If cash deals ever generate Loan records, revisit this.
    """
    months = _last_n_months(12)
    labels = [m.strftime("%b %y") for m in months]
    first_month = months[0]

    outflows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(posting_date, '%%Y-%%m-01') AS m,
               COALESCE(SUM(disbursed_amount), 0) AS total
        FROM `tabLoan Disbursement`
        WHERE docstatus = 1
          AND posting_date >= %s
        GROUP BY m
        """,
        (first_month,),
        as_dict=True,
    )

    inflows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(posting_date, '%%Y-%%m-01') AS m,
               COALESCE(SUM(amount_paid), 0) AS total
        FROM `tabLoan Repayment`
        WHERE docstatus = 1
          AND posting_date >= %s
        GROUP BY m
        """,
        (first_month,),
        as_dict=True,
    )

    out_map = {r.m: r.total for r in outflows}
    in_map = {r.m: r.total for r in inflows}

    return {
        "labels": labels,
        "datasets": [
            {
                "name": "Principal Advanced",
                "values": [out_map.get(m.strftime("%Y-%m-01"), 0) for m in months],
            },
            {
                "name": "Payments Received",
                "values": [in_map.get(m.strftime("%Y-%m-01"), 0) for m in months],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Chart 2: Past-Due Aging (Accounting workspace, half-width)
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def past_due_aging():
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
    today = nowdate()

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
        {"today": today},
        as_dict=True,
    )

    buckets = ["1-30", "31-60", "61-90", "90+"]
    totals = {r.bucket: r.total for r in rows}

    return {
        "labels": buckets,
        "datasets": [
            {
                "name": "Past-Due Amount",
                "values": [totals.get(b, 0) for b in buckets],
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Chart 3: New Deals by Financing Type (Deals workspace)
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def new_deals_by_type():
    """Monthly Home Build Request counts, stacked by financing_type.

    Last 12 months, two datasets: Cash and Floored. Stacking is enabled on the
    Dashboard Chart record via custom_options (not in this method).
    """
    months = _last_n_months(12)
    labels = [m.strftime("%b %y") for m in months]
    first_month = months[0]

    rows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(creation, '%%Y-%%m-01') AS m,
               financing_type,
               COUNT(*) AS n
        FROM `tabHome Build Request`
        WHERE docstatus = 1
          AND creation >= %s
        GROUP BY m, financing_type
        """,
        (first_month,),
        as_dict=True,
    )

    cash, floored = {}, {}
    for r in rows:
        if r.financing_type == "Cash":
            cash[r.m] = r.n
        elif r.financing_type == "Floored":
            floored[r.m] = r.n

    return {
        "labels": labels,
        "datasets": [
            {
                "name": "Cash",
                "values": [cash.get(m.strftime("%Y-%m-01"), 0) for m in months],
            },
            {
                "name": "Floored",
                "values": [floored.get(m.strftime("%Y-%m-01"), 0) for m in months],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _last_n_months(n):
    """First-day-of-month date objects for the last n months, oldest first.

    Includes the current month. Used to build chart labels and align bucketed
    SQL results onto a complete x-axis (so months with zero activity still
    render as empty bars, not skipped).
    """
    today = getdate(nowdate())
    return [getdate(get_first_day(add_months(today, -i))) for i in range(n - 1, -1, -1)]
