"""Dashboard Chart Source entrypoint for Inflows vs Outflows.

Frappe's Dashboard Chart with chart_type=Custom resolves `source` to this file
via the Dashboard Chart Source record, then calls `get()`. The framework
passes chart_name, filters, from_date, to_date, timespan, timegrain — our
methods ignore those (they return a fixed 12-month window). Accept **kwargs
so the call doesn't TypeError on the extras.

Logic lives in dcr.api.dashboard where tests cover it.
"""

from dcr.api.dashboard import inflows_vs_outflows as _impl


def get(**kwargs):  # noqa: ARG001 — Frappe passes framework kwargs we don't use
    return _impl()
