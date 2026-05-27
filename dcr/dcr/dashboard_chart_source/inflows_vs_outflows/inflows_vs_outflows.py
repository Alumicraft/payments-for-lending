"""Dashboard Chart Source entrypoint for Inflows vs Outflows.

Frappe's Dashboard Chart with chart_type=Custom resolves `source` to this file
via the Dashboard Chart Source record, then calls `get()`. Logic lives in
dcr.api.dashboard (where tests cover it); we re-export the function as get.
"""

from dcr.api.dashboard import inflows_vs_outflows as get  # noqa: F401
