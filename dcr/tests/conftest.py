"""Mock the frappe module before any dcr imports.

Frappe is not installed in the test environment — it lives inside the
bench virtualenv on the server. This conftest injects a minimal fake
so that our pure-logic tests can import dcr modules without error.
"""

import sys
from unittest.mock import MagicMock

# Create a mock frappe module hierarchy
frappe_mock = MagicMock()
frappe_mock._ = lambda x: x  # Translation passthrough
frappe_mock.throw = MagicMock(side_effect=Exception)
frappe_mock.whitelist = lambda **kw: (lambda fn: fn)  # No-op decorator

# Sub-modules that get imported
frappe_mock.utils = MagicMock()
frappe_mock.utils.now_datetime = MagicMock(return_value="2025-01-01 00:00:00")
frappe_mock.utils.getdate = lambda d: __import__("datetime").date.fromisoformat(str(d)[:10]) if d else None
frappe_mock.utils.today = MagicMock(return_value="2025-03-01")
frappe_mock.utils.add_days = lambda d, n: (
    __import__("datetime").date.fromisoformat(str(d)[:10]) + __import__("datetime").timedelta(days=n)
)
frappe_mock.utils.get_time = MagicMock()
frappe_mock.utils.nowtime = MagicMock()

frappe_model = MagicMock()
frappe_model.document = MagicMock()

# Inject into sys.modules so any `import frappe` finds our mock
sys.modules.setdefault("frappe", frappe_mock)
sys.modules.setdefault("frappe.utils", frappe_mock.utils)
sys.modules.setdefault("frappe.model", frappe_model)
sys.modules.setdefault("frappe.model.document", frappe_model.document)

# Make Document a real base class so our doctypes can subclass it
class _Document:
    pass

frappe_model.document.Document = _Document
