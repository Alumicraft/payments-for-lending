import json
import os

import frappe


def _read_map_asset(*relparts):
    """Read a map-block asset (HTML/JS) shipped under dcr/public/.
    The ~1500-line map block lives in real asset files
    (public/html/map_block.html, public/js/map_block.js) rather than as
    inline string literals, and is loaded into the Custom HTML Block at
    setup/migrate time."""
    path = os.path.join(os.path.dirname(__file__), "public", *relparts)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _html_block_js_field():
    """Return the Custom HTML Block column that stores JS (the fieldname
    differs by Frappe version), or None if none is present."""
    for candidate in ("script", "javascript", "js"):
        if frappe.db.has_column("Custom HTML Block", candidate):
            return candidate
    return None


def after_install():
    """Ensure DCR module definition and required groups exist."""
    # Map block first — isolated so any later setup failure cannot block it.
    try:
        ensure_map_block()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_map_block failed")

    if not frappe.db.exists("Module Def", "DCR"):
        frappe.get_doc({
            "doctype": "Module Def",
            "module_name": "DCR",
            "app_name": "dcr",
        }).insert(ignore_permissions=True)

    # Supplier Groups
    for group_name in ("Escrow", "Factory"):
        if not frappe.db.exists("Supplier Group", group_name):
            frappe.get_doc({
                "doctype": "Supplier Group",
                "supplier_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Customer Groups
    for group_name in ("Home Buyer", "Dealer"):
        if not frappe.db.exists("Customer Group", group_name):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": group_name,
            }).insert(ignore_permissions=True)

    # Workspaces — created without a module so Frappe does not treat them
    # as "orphan" standard content and delete them during migrations.
    for ws in ("Overview", "Deals", "Accounting", "Contacts", "Access"):
        if not frappe.db.exists("Workspace", ws):
            frappe.get_doc({
                "doctype": "Workspace",
                "label": ws,
                "title": ws,
                "public": 1,
            }).insert(ignore_permissions=True)

    # Number Card: Users Online
    card_name = "Users Online"
    if not frappe.db.exists("Number Card", card_name):
        frappe.get_doc({
            "doctype": "Number Card",
            "name": card_name,
            "label": card_name,
            "type": "Custom",
            "method": "dcr.api.sessions.get_active_sessions",
            "is_public": 1,
            "owner": "Administrator",
        }).insert(ignore_permissions=True)

    # Dashboard Chart: Active Users Per Day
    chart_name = "Active Users Per Day"
    if not frappe.db.exists("Dashboard Chart", chart_name):
        frappe.get_doc({
            "doctype": "Dashboard Chart",
            "chart_name": chart_name,
            "chart_type": "Report",
            "report_name": "Daily Active Users",
            "x_field": "date",
            "filters_json": "{}",
            "type": "Line",
            "is_public": 1,
            "owner": "Administrator",
            "y_axis": [{"y_field": "active_users", "parentfield": "y_axis"}],
        }).insert(ignore_permissions=True)

    # NOTE: Number Card and Dashboard Chart are created above but NOT
    # added to the workspace programmatically.  Calling .save() on a
    # Workspace rebuilds its child tables from the `content` JSON field,
    # which wipes any cards/charts placed via the Workspace Builder.
    # Add them manually: Workspace Builder → Access → drag in the card/chart.

    # Frappe's `sync_fixtures` re-imports ERPNext Workspace JSON on every
    # migrate, restoring chart/card references to docs we've since deleted.
    # Stale refs in `content` blocks render with width 0 → negative SVG rect
    # widths → frappe-charts retries forever → workspace skeleton hangs.
    # Sweep orphans after fixtures have synced.
    try:
        from dcr.api.repair import _purge_orphan_workspace_refs
        _purge_orphan_workspace_refs(dry_run=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "purge_orphan_workspace_refs (after_install)")

    # The patches.txt entry runs the LA-connections cleanup once; the
    # standard Lending app re-syncs Loan Application's DocType Links on
    # every migrate, which resets our changes. Re-apply post-migrate.
    try:
        tidy_la_connections()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "tidy_la_connections (after_install)")

    # Idempotent field/option syncs. Each runs in isolation so one failure
    # can't block the rest; the log label matches the function name.
    for fn in (
        ensure_bank_account_types,
        ensure_bank_account_ach_fields,
        ensure_supplier_geo_fields,
        ensure_order_hbr_fields,
        ensure_payment_entry_calculated_fields,
        ensure_loan_application_field_repairs,
        ensure_hbr_stage_field_options,
        sync_existing_hbr_stage_fields,
        ensure_factory_addresses,
        ensure_dcr_dashboard_configuration,
        ensure_hbr_kanban_columns,
        ensure_loan_demand_offset_order,
        ensure_lending_accounting_defaults,
    ):
        try:
            fn()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{fn.__name__} failed")

    frappe.db.commit()


FACTORY_ADDRESSES = {
    "Durango Homes": {
        "address_line1": "2502 W Durango St",
        "city": "Phoenix",
        "state": "AZ",
        "pincode": "85009",
    },
    "Fleetwood Homes": {
        "address_line1": "3636 N Central Ave",
        "address_line2": "Suite 1200",
        "city": "Phoenix",
        "state": "AZ",
        "pincode": "85012",
    },
    "Skyline Homes": {
        "address_line1": "6420 W Allison Rd",
        "city": "Chandler",
        "state": "AZ",
        "pincode": "85226",
    },
    "Champion Home Builders": {
        "address_line1": "6420 W Allison Rd",
        "city": "Chandler",
        "state": "AZ",
        "pincode": "85226",
    },
}


def ensure_factory_addresses():
    """Repair primary Phoenix-area addresses for imported factory suppliers."""
    if not frappe.db.exists("DocType", "Address"):
        return

    from dcr.api.map import geocode_supplier

    for supplier_name, values in FACTORY_ADDRESSES.items():
        if not frappe.db.exists("Supplier", supplier_name):
            continue

        address_title = f"{supplier_name} Factory"
        address_name = frappe.db.exists("Address", {"address_title": address_title})
        address_changed = False
        if not address_name:
            address = frappe.get_doc({
                "doctype": "Address",
                "address_title": address_title,
                "address_type": "Shipping",
                "is_primary_address": 1,
                "country": "United States",
                "links": [{
                    "link_doctype": "Supplier",
                    "link_name": supplier_name,
                }],
                **values,
            })
            address.insert(ignore_permissions=True)
            address_name = address.name
            address_changed = True
        else:
            address = frappe.get_doc("Address", address_name)
            desired = {
                "address_type": "Shipping",
                "is_primary_address": 1,
                "country": "United States",
                "address_line2": "",
                **values,
            }
            for fieldname, value in desired.items():
                if (address.get(fieldname) or "") != value:
                    address.set(fieldname, value)
                    address_changed = True
            if address_changed:
                address.save(ignore_permissions=True)

        if frappe.db.has_column("Supplier", "supplier_primary_address"):
            frappe.db.set_value(
                "Supplier",
                supplier_name,
                "supplier_primary_address",
                address_name,
                update_modified=False,
            )
        if address_changed:
            # Never leave a corrected Phoenix-area address attached to stale
            # California coordinates if geocoding is temporarily unavailable.
            frappe.db.set_value(
                "Supplier",
                supplier_name,
                {"latitude": 0, "longitude": 0},
                update_modified=False,
            )
        geocode_supplier(frappe.get_doc("Supplier", supplier_name))


def submit_imported_factory_assignments():
    """Submit active assignments already marked Approved by the dealer import."""
    names = frappe.get_all(
        "Factory Assignment",
        filters={
            "docstatus": 0,
            "active": 1,
            "retailer_application_status": "Approved",
        },
        pluck="name",
    )
    for name in names:
        frappe.get_doc("Factory Assignment", name).submit()


def ensure_dcr_dashboard_configuration():
    """Repair DCR cards and add the shipped custom charts to their workspaces."""
    card_updates = {
        "Pending Deals": {
            "label": "Pending Deals",
            "type": "Document Type",
            "document_type": "Home Build Request",
            "function": "Count",
            "aggregate_function_based_on": None,
            # A pending deal is an HBR the team saved but has not submitted.
            # Do not use custom_order_stage here: both drafts and submitted
            # requests without a PO store the backend value "Pending".
            "filters_json": json.dumps([
                ["Home Build Request", "docstatus", "=", 0],
            ]),
            "dynamic_filters_json": "[]",
            "show_percentage_stats": 0,
        },
        "New Dealers Pending": {
            "label": "New Dealers Pending",
            "type": "Document Type",
            "document_type": "Customer",
            "function": "Count",
            "aggregate_function_based_on": None,
            "filters_json": json.dumps([
                ["Customer", "customer_group", "=", "Dealer"],
                ["Customer", "disabled", "=", 0],
                ["Customer", "dealer_agreement_status", "=", "Sent"],
            ]),
            "show_percentage_stats": 0,
        },
        "Active Dealers": {
            "label": "Active Dealers",
            "type": "Document Type",
            "document_type": "Customer",
            "function": "Count",
            "aggregate_function_based_on": None,
            "filters_json": json.dumps([
                ["Customer", "customer_group", "=", "Dealer"],
                ["Customer", "disabled", "=", 0],
            ]),
        },
        "Cash Collected MTD": {
            "label": "Cash Collected MTD",
            "type": "Custom",
            "document_type": "Loan Repayment",
            "method": "dcr.api.dashboard.cash_collected_mtd",
            "currency": "USD",
            "filters_json": "[]",
            "dynamic_filters_json": "[]",
            "show_percentage_stats": 0,
            # Frappe v16's compact-number helper turns numeric zero into an
            # empty string, which the currency formatter then parses as NaN.
            "show_full_number": 1,
        },
    }
    for card_name, updates in card_updates.items():
        if frappe.db.exists("Number Card", card_name):
            frappe.db.set_value("Number Card", card_name, updates)
            frappe.clear_document_cache("Number Card", card_name)

    _ensure_workspace_chart("Accounting", "Repayment Breakdown", 6)
    _ensure_workspace_chart("Deals", "Deal Pipeline by Factory", 12)


def _ensure_workspace_chart(workspace_name, chart_name, col):
    if not (
        frappe.db.exists("Workspace", workspace_name)
        and frappe.db.exists("Dashboard Chart", chart_name)
    ):
        return

    workspace = frappe.get_doc("Workspace", workspace_name)
    raw_content = workspace.content or "[]"
    try:
        content = json.loads(raw_content)
    except (TypeError, ValueError):
        return

    has_block = any(
        block.get("type") == "chart"
        and block.get("data", {}).get("chart_name") == chart_name
        for block in content
    )
    if not has_block:
        content.append({
            "type": "chart",
            "data": {"chart_name": chart_name, "col": col},
        })

    has_chart_row = any(
        row.get("chart_name") == chart_name
        for row in workspace.get("charts") or []
    )
    if not has_chart_row:
        workspace.append("charts", {
            "chart_name": chart_name,
            "label": chart_name,
        })

    # Frappe requires both the visual content block and a Workspace Chart
    # child row. Updating only content leaves a valid-looking block that the
    # renderer silently skips.
    workspace.content = json.dumps(content)
    workspace.save(ignore_permissions=True)
    frappe.clear_document_cache("Workspace", workspace_name)


def ensure_hbr_kanban_columns():
    """Align the HBR board with the backend-derived deal lifecycle.

    The board was created with a "Not Ordered" column while HBR records store
    the canonical value "Pending". Frappe only renders a card when its value
    exactly matches a column name, so all pending requests were invisible.
    Draft HBRs use the separate canonical value "Draft", displayed as Pending.
    """
    if not frappe.db.exists("DocType", "Kanban Board"):
        return

    board_names = frappe.get_all(
        "Kanban Board",
        filters={"reference_doctype": "Home Build Request"},
        pluck="name",
    )
    for board_name in board_names:
        board = frappe.get_doc("Kanban Board", board_name)
        changed = False
        active_filter = json.dumps([
            ["Home Build Request", "docstatus", "in", [0, 1]],
        ])
        if board.get("filters") != active_filter:
            board.filters = active_filter
            changed = True

        desired_columns = ["Draft", "Pending", "Ordered", "Delivered"]
        columns_by_name = {}
        for column in list(board.get("columns") or []):
            if column.get("column_name") == "Not Ordered":
                column.column_name = "Pending"
                changed = True
            if (
                column.column_name in desired_columns
                and column.column_name not in columns_by_name
            ):
                columns_by_name[column.column_name] = column

        for column_name in desired_columns:
            if column_name not in columns_by_name:
                columns_by_name[column_name] = board.append(
                    "columns", {"column_name": column_name}
                )
                changed = True

        ordered_columns = [columns_by_name[name] for name in desired_columns]
        if list(board.get("columns") or []) != ordered_columns:
            board.columns = ordered_columns
            changed = True
        if changed:
            board.save(ignore_permissions=True)
            frappe.clear_document_cache("Kanban Board", board_name)


def ensure_lending_accounting_defaults():
    """Repair DCR Lending account mappings required for demand generation."""
    if not frappe.db.exists("DocType", "Loan Product") or not frappe.db.exists("DocType", "Account"):
        return

    receivable_account = "10202 - Loans Receivable - DCR"
    fallback_receivable_account = "10201 - Accounts Receivable (NON QBO) - DCR"
    income_account = "40110 - Service/Fee Income - DCR"
    write_off_account = "50282 - Bad Debt - DCR"

    for account in (receivable_account, fallback_receivable_account):
        if frappe.db.exists("Account", account):
            current_type = frappe.db.get_value("Account", account, "account_type")
            if current_type != "Receivable":
                frappe.db.set_value("Account", account, "account_type", "Receivable", update_modified=False)

    if not frappe.db.exists("Account", receivable_account):
        return

    loan_products = frappe.get_all(
        "Loan Product",
        filters={"company": "Dealer Capital Resources"},
        fields=["name"],
    )

    receivable_fields = (
        "loan_account",
        "security_deposit_account",
        "customer_refund_account",
        "interest_receivable_account",
        "penalty_receivable_account",
    )
    accrual_fields = (
        "interest_accrued_account",
        "penalty_accrued_account",
    )
    income_fields = (
        "interest_income_account",
        "interest_waiver_account",
        "broken_period_interest_recovery_account",
        "penalty_income_account",
        "penalty_waiver_account",
        "write_off_recovery_account",
    )

    for product in loan_products:
        product_name = product.name if hasattr(product, "name") else product.get("name")
        updates = {}

        for fieldname in receivable_fields:
            if not frappe.db.has_column("Loan Product", fieldname):
                continue

            current = frappe.db.get_value("Loan Product", product_name, fieldname)
            if not current or not _account_is_type(current, "Receivable"):
                updates[fieldname] = receivable_account

        for fieldname in income_fields:
            if not frappe.db.has_column("Loan Product", fieldname):
                continue

            current = frappe.db.get_value("Loan Product", product_name, fieldname)
            if not current and frappe.db.exists("Account", income_account):
                updates[fieldname] = income_account

        for fieldname in accrual_fields:
            if not frappe.db.has_column("Loan Product", fieldname):
                continue

            current = frappe.db.get_value("Loan Product", product_name, fieldname)
            if (
                not current or current == receivable_account or _account_is_type(current, "Receivable")
            ) and frappe.db.exists("Account", income_account):
                updates[fieldname] = income_account

        if (
            frappe.db.has_column("Loan Product", "write_off_account")
            and not frappe.db.get_value("Loan Product", product_name, "write_off_account")
            and frappe.db.exists("Account", write_off_account)
        ):
            updates["write_off_account"] = write_off_account

        if updates:
            frappe.db.set_value("Loan Product", product_name, updates, update_modified=False)

    frappe.clear_cache(doctype="Loan Product")
    frappe.clear_cache(doctype="Account")


def _account_is_type(account, account_type):
    if not account or not frappe.db.exists("Account", account):
        return False
    return frappe.db.get_value("Account", account, "account_type") == account_type


def ensure_loan_demand_offset_order():
    """Repair Lending's collection offset setup for repayment entry.

    Some upgraded Lending sites keep old Select values such as
    ``IP...IP...IP...CCC`` in Company collection-offset fields after those
    fields become Links. Repayment save then tries to load a missing
    Loan Demand Offset Order. Keep a valid standard order present and point
    stale company values at it.
    """
    if not frappe.db.exists("DocType", "Loan Demand Offset Order"):
        return

    order_name = "DCR Standard Loan Demand Offset Order"
    components = [
        {"demand_type": "EMI (Principal + Interest)"},
        {"demand_type": "Penalty"},
        {"demand_type": "Charges"},
        {"demand_type": "Principal"},
    ]
    if not frappe.db.exists("Loan Demand Offset Order", order_name):
        order = frappe.get_doc({
            "doctype": "Loan Demand Offset Order",
            "title": order_name,
            "components": components,
        })
        order.insert(ignore_permissions=True)
    else:
        order = frappe.get_doc("Loan Demand Offset Order", order_name)
        current = [row.demand_type for row in order.get("components")]
        expected = [row["demand_type"] for row in components]
        if current != expected:
            order.set("components", components)
            order.save(ignore_permissions=True)

    fields = (
        "collection_offset_sequence_for_standard_asset",
        "collection_offset_sequence_for_sub_standard_asset",
        "collection_offset_sequence_for_written_off_asset",
        "collection_offset_sequence_for_settlement_collection",
    )

    for company in frappe.get_all("Company", pluck="name"):
        updates = {}
        for fieldname in fields:
            if not frappe.db.has_column("Company", fieldname):
                continue
            current = frappe.db.get_value("Company", company, fieldname)
            if current and frappe.db.exists("Loan Demand Offset Order", current):
                continue
            updates[fieldname] = order_name

        if updates:
            frappe.db.set_value("Company", company, updates, update_modified=False)

    frappe.clear_cache(doctype="Company")


def ensure_supplier_geo_fields():
    """Create hidden latitude/longitude custom fields on Supplier.

    Used by the map block to plot factory icons. Hidden because they are
    populated automatically from the supplier's primary address — users
    should not edit them directly.
    """
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field

    fields = [
        {
            "fieldname": "latitude",
            "label": "Latitude",
            "fieldtype": "Float",
            "precision": "6",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "supplier_group",
        },
        {
            "fieldname": "longitude",
            "label": "Longitude",
            "fieldtype": "Float",
            "precision": "6",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "latitude",
        },
    ]
    for f in fields:
        if not frappe.db.exists("Custom Field", {"dt": "Supplier", "fieldname": f["fieldname"]}):
            create_custom_field("Supplier", f)


def ensure_bank_account_ach_fields():
    """Create Bank Account fields required by the ACH payment flow.

    Frappe Cloud runs patches during deploy, so the Bank Account migration
    cannot depend on these fields being added manually in Customize Form.
    """
    fields = [
        {
            "fieldname": "custom_ach_status",
            "label": "ACH Status",
            "fieldtype": "Select",
            "options": "\nActive\nPaused\nRevoked\nFailed",
            "insert_after": "is_default",
        },
        {
            "fieldname": "custom_achq_token",
            "label": "ACHQ Token",
            "fieldtype": "Data",
            "hidden": 1,
            "no_copy": 1,
            "insert_after": "custom_ach_status",
        },
        {
            "fieldname": "custom_token_source",
            "label": "Token Source",
            "fieldtype": "Select",
            "options": "\nManual\nPlaid",
            "read_only": 1,
            "insert_after": "custom_achq_token",
        },
        {
            "fieldname": "custom_account_last_four",
            "label": "Account Last 4",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "custom_token_source",
        },
        {
            "fieldname": "custom_routing_last_4",
            "label": "Routing Last 4",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "custom_account_last_four",
        },
        {
            "fieldname": "custom_verification_status",
            "label": "Verification Status",
            "fieldtype": "Select",
            "options": "\nPOS\nUNK\nNEG",
            "read_only": 1,
            "insert_after": "custom_routing_last_4",
        },
        {
            "fieldname": "custom_consent_captured",
            "label": "Consent Captured",
            "fieldtype": "Check",
            "read_only": 1,
            "insert_after": "custom_verification_status",
        },
        {
            "fieldname": "custom_authorization_ip",
            "label": "Authorization IP",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "custom_consent_captured",
        },
        {
            "fieldname": "custom_authorization_date",
            "label": "Authorization Date",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "custom_authorization_ip",
        },
        {
            "fieldname": "custom_sec_code",
            "label": "SEC Code",
            "fieldtype": "Select",
            "options": "WEB\nPPD\nCCD\nTEL",
            "default": "CCD",
            "insert_after": "custom_authorization_date",
        },
        {
            "fieldname": "custom_revocation_date",
            "label": "Revocation Date",
            "fieldtype": "Datetime",
            "read_only": 1,
            "insert_after": "custom_sec_code",
        },
        {
            "fieldname": "custom_revocation_reason",
            "label": "Revocation Reason",
            "fieldtype": "Small Text",
            "insert_after": "custom_revocation_date",
        },
        {
            "fieldname": "custom_legacy_ach_auth",
            "label": "Legacy ACH Authorization",
            "fieldtype": "Link",
            "options": "ACH Authorization",
            "read_only": 1,
            "hidden": 1,
            "no_copy": 1,
            "insert_after": "custom_revocation_reason",
        },
    ]

    created = False
    for field in fields:
        if frappe.db.exists("Custom Field", {"dt": "Bank Account", "fieldname": field["fieldname"]}):
            continue

        payload = {
            "doctype": "Custom Field",
            "dt": "Bank Account",
            **field,
        }
        frappe.get_doc(payload).insert(ignore_permissions=True)
        created = True

    if created:
        frappe.clear_cache(doctype="Bank Account")


def ensure_bank_account_types():
    """Install the ACH account types required by Bank Account link fields."""
    if not frappe.db.exists("DocType", "Bank Account Type"):
        return

    for account_type in ("Checking", "Savings"):
        if frappe.db.exists("Bank Account Type", account_type):
            continue
        frappe.get_doc({
            "doctype": "Bank Account Type",
            "account_type": account_type,
        }).insert(ignore_permissions=True)


def ensure_purchase_order_hbr_field():
    """Create the Purchase Order link used by HBR create buttons and map status."""
    ensure_order_hbr_fields(["Purchase Order"])


def ensure_order_hbr_fields(only_doctypes=None):
    """Create missing HBR link fields on order/payment doctypes.

    Existing fields are intentionally left untouched so Customize Form remains
    the source of truth for placement and layout after first provisioning.
    The link itself must stay writable/copyable: Frappe's dashboard connection
    create path applies defaults through route options, and get_new_doc skips
    fields marked no_copy.
    """
    fields = [
        {
            "dt": "Purchase Order",
            "fieldname": "custom_home_build_request",
            "insert_after": "supplier",
        },
        {
            "dt": "Purchase Invoice",
            "fieldname": "home_build_request",
            "insert_after": "supplier",
        },
        {
            "dt": "Purchase Receipt",
            "fieldname": "custom_home_build_request",
            "insert_after": "supplier",
        },
        {
            "dt": "Payment Entry",
            "fieldname": "custom_home_build_request",
            "insert_after": "party",
        },
    ]
    if only_doctypes:
        only_doctypes = set(only_doctypes)
        fields = [field for field in fields if field["dt"] in only_doctypes]

    for field in fields:
        existing = frappe.db.exists(
            "Custom Field",
            {"dt": field["dt"], "fieldname": field["fieldname"]},
        )
        if existing:
            changed = False
            if frappe.db.get_value("Custom Field", existing, "read_only"):
                frappe.db.set_value("Custom Field", existing, "read_only", 0)
                changed = True
            if frappe.db.get_value("Custom Field", existing, "no_copy"):
                frappe.db.set_value("Custom Field", existing, "no_copy", 0)
                changed = True
            if changed:
                frappe.clear_cache(doctype=field["dt"])
            continue

        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": field["dt"],
            "fieldname": field["fieldname"],
            "label": "Home Build Request",
            "fieldtype": "Link",
            "options": "Home Build Request",
            "insert_after": field["insert_after"],
            "read_only": 0,
            "no_copy": 0,
        }).insert(ignore_permissions=True)
        frappe.clear_cache(doctype=field["dt"])


def ensure_payment_entry_calculated_fields():
    """Install calculated Payment Entry fields owned by the DCR client app."""
    fieldname = "custom_total_outstanding"
    existing = frappe.db.exists(
        "Custom Field",
        {"dt": "Payment Entry", "fieldname": fieldname},
    )
    if not existing:
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Payment Entry",
            "fieldname": fieldname,
            "label": "Selected Outstanding",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "insert_after": "total_allocated_amount",
            "read_only": 1,
            "no_copy": 1,
        }).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Payment Entry")

    # This legacy site Client Script duplicated app logic, referenced the field
    # before it existed, and dirtied submitted Payment Entries on every refresh.
    legacy_script = frappe.db.exists(
        "Client Script",
        "Payment Entry - Get Outstanding Balance of Reference Invoices",
    )
    if legacy_script and frappe.db.get_value("Client Script", legacy_script, "enabled"):
        frappe.db.set_value("Client Script", legacy_script, "enabled", 0)
        frappe.clear_cache(doctype="Payment Entry")


def ensure_loan_application_field_repairs():
    """Keep Lending fields aligned with DCR's current HBR and dealer data."""
    floor_plan_field = frappe.db.exists(
        "Custom Field",
        {"dt": "Loan Application", "fieldname": "floor_plan"},
    )
    if floor_plan_field:
        fetch_from = frappe.db.get_value("Custom Field", floor_plan_field, "fetch_from")
        if fetch_from != "home_build_request.floor_plan":
            frappe.db.set_value(
                "Custom Field",
                floor_plan_field,
                "fetch_from",
                "home_build_request.floor_plan",
            )

    phone_options_name = "Loan Application-applicant_phone_number-options"
    phone_options = frappe.db.exists("Property Setter", phone_options_name)
    if not phone_options:
        frappe.get_doc({
            "doctype": "Property Setter",
            "name": phone_options_name,
            "doc_type": "Loan Application",
            "doctype_or_field": "DocField",
            "field_name": "applicant_phone_number",
            "property": "options",
            "property_type": "Data",
            "value": "country",
        }).insert(ignore_permissions=True)
    elif frappe.db.get_value("Property Setter", phone_options_name, "value") != "country":
        frappe.db.set_value("Property Setter", phone_options_name, "value", "country")

    # Repair older submitted applications that were saved before address
    # hydration existed. Database writes are deliberate here: normal document
    # saves reject these standard fields after submit.
    from dcr.api.lending import _get_customer_address_details

    applications = frappe.get_all(
        "Loan Application",
        filters={"docstatus": 1, "applicant_type": "Customer"},
        fields=[
            "name",
            "applicant",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "zip_code",
            "country",
        ],
    )
    address_fields = (
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "zip_code",
        "country",
    )
    for application in applications:
        get_value = (
            (lambda fieldname: getattr(application, fieldname, None))
            if hasattr(application, "name")
            else application.get
        )
        missing = [fieldname for fieldname in address_fields if not get_value(fieldname)]
        if not missing:
            continue
        address = _get_customer_address_details(get_value("applicant"))
        updates = {
            fieldname: address.get(fieldname)
            for fieldname in missing
            if address.get(fieldname)
        }
        if updates:
            frappe.db.set_value(
                "Loan Application",
                get_value("name"),
                updates,
                update_modified=False,
            )

    frappe.clear_cache(doctype="Loan Application")


def ensure_hbr_stage_field_options():
    """Keep HBR stage Custom Field options aligned with derived stage values.

    The HBR stage fields are placed through Customize Form on Frappe Cloud, so
    this only updates existing field options and leaves layout untouched.
    """
    fields = {
        "custom_order_stage": "Draft\nPending\nOrdered\nDelivered\nClosed",
        "custom_loan_stage": (
            "Not Applicable\nNot Started\nApplied\nApproved\nFunded\nActive\nClosed"
        ),
    }

    changed = False
    for fieldname, options in fields.items():
        custom_field = frappe.db.exists(
            "Custom Field",
            {"dt": "Home Build Request", "fieldname": fieldname},
        )
        if not custom_field:
            continue

        updates = {}
        current_options = frappe.db.get_value("Custom Field", custom_field, "options")
        if current_options != options:
            updates["options"] = options
        if frappe.db.get_value("Custom Field", custom_field, "read_only") != 1:
            updates["read_only"] = 1
        if frappe.db.get_value("Custom Field", custom_field, "allow_on_submit") != 0:
            updates["allow_on_submit"] = 0
        if frappe.db.get_value("Custom Field", custom_field, "reqd") != 0:
            updates["reqd"] = 0

        if not updates:
            continue

        frappe.db.set_value("Custom Field", custom_field, updates)
        changed = True

    if changed:
        frappe.clear_cache(doctype="Home Build Request")


def sync_existing_hbr_stage_fields():
    """Backfill derived stage fields for existing HBRs after migrations."""
    from dcr.api.hbr_stage import sync_hbr_stages

    for row in frappe.get_all("Home Build Request", pluck="name"):
        sync_hbr_stages(row)


def tidy_la_connections():
    """Mirror dcr.patches.tidy_la_connections so it survives re-syncs.

    - Hide stock "Loan Security Assignment" link (DCR runs unsecured loans).
    - Group the stock "Loan" link under "Lending" so the LA connections
      panel renders with a header matching HBR's grouping.
    """
    lsa_links = frappe.get_all(
        "DocType Link",
        filters={
            "parent": "Loan Application",
            "parenttype": "DocType",
            "link_doctype": "Loan Security Assignment",
        },
        pluck="name",
    )
    for name in lsa_links:
        if not frappe.db.get_value("DocType Link", name, "hidden"):
            frappe.db.set_value("DocType Link", name, "hidden", 1)

    loan_links = frappe.get_all(
        "DocType Link",
        filters={
            "parent": "Loan Application",
            "parenttype": "DocType",
            "link_doctype": "Loan",
        },
        pluck="name",
    )
    for name in loan_links:
        if frappe.db.get_value("DocType Link", name, "group") != "Lending":
            frappe.db.set_value("DocType Link", name, "group", "Lending")

    frappe.clear_cache(doctype="Loan Application")


@frappe.whitelist()
def force_refresh_map_block():
    """Diagnostic: force re-run ensure_map_block and return live DB state.

    Call from browser console:
      frappe.call('dcr.setup.force_refresh_map_block').then(r => console.log(r.message))
    """
    frappe.only_for("System Manager")

    def snapshot(name):
        if not frappe.db.exists("Custom HTML Block", name):
            return None
        row = frappe.db.get_value(
            "Custom HTML Block", name,
            ["modified", "html", "script"], as_dict=True,
        )
        script = row.script or ""
        return {
            "name": name,
            "modified": str(row.modified),
            "html_preview": (row.html or "")[:120],
            "script_length": len(script),
            "script_head": script[:180],
            "script_tail": script[-180:] if len(script) > 180 else "",
        }

    js_field = _html_block_js_field()

    def workspace_refs():
        """Return {workspace_name: {mentions_map, mentions_legacy, snippet}} for
        any Workspace whose content references either block name."""
        out = {}
        for name in ("Map", "HBR Heatmap"):
            rows = frappe.get_all(
                "Workspace",
                filters={"content": ["like", f"%{name}%"]},
                pluck="name",
            )
            for ws in rows:
                if ws in out:
                    continue
                content = frappe.db.get_value("Workspace", ws, "content") or ""
                idx = content.find("HBR Heatmap")
                if idx == -1:
                    idx = content.find("Map")
                snippet = content[max(0, idx - 40):idx + 80] if idx != -1 else ""
                out[ws] = {
                    "mentions_map": "Map" in content,
                    "mentions_legacy": "HBR Heatmap" in content,
                    "snippet": snippet,
                }
        return out

    before = {
        "blocks": {
            "Map": snapshot("Map"),
            "HBR Heatmap": snapshot("HBR Heatmap"),
        },
        "workspaces": workspace_refs(),
    }

    error = None
    try:
        ensure_map_block()
        frappe.db.commit()
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        frappe.log_error(frappe.get_traceback(), "force_refresh_map_block")

    after = {
        "blocks": {
            "Map": snapshot("Map"),
            "HBR Heatmap": snapshot("HBR Heatmap"),
        },
        "workspaces": workspace_refs(),
    }

    return {
        "js_field_detected": js_field,
        "before": before,
        "after": after,
        "error": error,
    }


def ensure_map_block():
    """Create or update the workspace map Custom HTML Block."""
    block_name = "Map"
    legacy_block_name = "HBR Heatmap"

    # One-time migration from legacy name — rename the doc if the legacy name
    # is still present.
    if (
        frappe.db.exists("Custom HTML Block", legacy_block_name)
        and not frappe.db.exists("Custom HTML Block", block_name)
    ):
        frappe.rename_doc(
            "Custom HTML Block", legacy_block_name, block_name,
            force=True, merge=False,
        )

    # Patch Workspace content unconditionally. The workspace's `content` JSON
    # stores the block name as a raw string reference, and the rename above
    # does NOT propagate into that field. We keep this outside the rename
    # branch so a workspace left pointing at the legacy name (because the
    # rename ran successfully on an earlier migrate but the content patch
    # didn't match) still gets healed on the next boot.
    legacy_workspaces = frappe.get_all(
        "Workspace",
        filters={"content": ["like", f"%{legacy_block_name}%"]},
        pluck="name",
    )
    for ws in legacy_workspaces:
        content = frappe.db.get_value("Workspace", ws, "content") or ""
        if legacy_block_name in content:
            frappe.db.set_value(
                "Workspace", ws, "content",
                content.replace(legacy_block_name, block_name),
            )
            frappe.clear_document_cache("Workspace", ws)
    if legacy_workspaces:
        frappe.db.commit()

    html_content = _read_map_asset("html", "map_block.html")
    js_content = _read_map_asset("js", "map_block.js")

    # Detect the correct fieldname for JS (differs by Frappe version)
    js_field = _html_block_js_field()

    if frappe.db.exists("Custom HTML Block", block_name):
        updates = {"html": html_content}
        if js_field:
            updates[js_field] = js_content
        # IMPORTANT: update_modified must be True (default) so the block's
        # `modified` timestamp bumps. Frappe's desk HTTP cache keys off
        # `modified` — without a bump, browsers get the stale rendered HTML
        # even though the DB row is new.
        frappe.db.set_value("Custom HTML Block", block_name, updates)
        frappe.db.commit()
        # Clear Frappe's in-process doc cache
        frappe.clear_document_cache("Custom HTML Block", block_name)
        # Bust any Workspace that embeds this block — the workspace render
        # is cached by its own `modified`, so we need to touch every workspace
        # referencing this block in its content JSON.
        workspaces = frappe.get_all(
            "Workspace",
            filters={"content": ["like", f"%{block_name}%"]},
            pluck="name",
        )
        for ws in workspaces:
            frappe.db.set_value("Workspace", ws, "modified", frappe.utils.now())
            frappe.clear_document_cache("Workspace", ws)
        frappe.db.commit()
    else:
        new_doc = {
            "doctype": "Custom HTML Block",
            "name": block_name,
            "html": html_content,
            "private": 0,
        }
        if js_field:
            new_doc[js_field] = js_content
        frappe.get_doc(new_doc).insert(ignore_permissions=True)
