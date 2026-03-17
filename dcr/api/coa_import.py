import frappe
from frappe import _
from frappe.utils.nestedset import rebuild_tree
import openpyxl


# QBO type → (root_type, account_type, intermediate_group_name)
QBO_TYPE_MAP = {
    "Bank":                      ("Asset",     "Bank",              "Bank Accounts"),
    "Accounts receivable (A/R)": ("Asset",     "Receivable",        "Accounts Receivable"),
    "Other Current Assets":      ("Asset",     "Current Asset",     "Current Assets"),
    "Other Assets":              ("Asset",     "Fixed Asset",       "Other Assets"),
    "Accounts payable (A/P)":    ("Liability", "Payable",           "Accounts Payable"),
    "Credit Card":               ("Liability", "Bank",              "Credit Cards"),
    "Other Current Liabilities": ("Liability", "Liability",         "Current Liabilities"),
    "Long Term Liabilities":     ("Liability", "Liability",         "Long Term Liabilities"),
    "Equity":                    ("Equity",    "Equity",            None),
    "Income":                    ("Income",    "Income Account",    "Direct Income"),
    "Other Income":              ("Income",    "Income Account",    "Other Income"),
    "Cost of Goods Sold":        ("Expense",   "Cost of Goods Sold","Cost of Goods Sold"),
    "Expenses":                  ("Expense",   "Expense Account",   "Operating Expenses"),
    "Other Expense":             ("Expense",   "Expense Account",   "Other Expenses"),
}

ROOT_ACCOUNTS = {
    "Asset":     {"name": "Assets",      "number": "10000"},
    "Liability": {"name": "Liabilities", "number": "20000"},
    "Equity":    {"name": "Equity",      "number": "30000"},
    "Income":    {"name": "Income",      "number": "40000"},
    "Expense":   {"name": "Expenses",    "number": "50000"},
}

INTERMEDIATE_GROUPS = {
    "Bank Accounts":       {"number": "10100", "root_type": "Asset"},
    "Current Assets":      {"number": "10200", "root_type": "Asset"},
    "Other Assets":        {"number": "10300", "root_type": "Asset"},
    "Accounts Receivable": {"number": "10400", "root_type": "Asset"},
    "Accounts Payable":    {"number": "20100", "root_type": "Liability"},
    "Credit Cards":        {"number": "20200", "root_type": "Liability"},
    "Current Liabilities": {"number": "20300", "root_type": "Liability"},
    "Long Term Liabilities": {"number": "20400", "root_type": "Liability"},
    "Direct Income":       {"number": "40100", "root_type": "Income"},
    "Other Income":        {"number": "40200", "root_type": "Income"},
    "Cost of Goods Sold":  {"number": "50100", "root_type": "Expense"},
    "Operating Expenses":  {"number": "50200", "root_type": "Expense"},
    "Other Expenses":      {"number": "50300", "root_type": "Expense"},
}


def _delete_existing_accounts(company, dry_run=False):
    """Delete all existing accounts for the company using direct SQL."""
    result = {"deleted": 0, "errors": []}

    count = frappe.db.count("Account", {"company": company})
    result["deleted"] = count

    if dry_run or count == 0:
        return result

    # Unset company default account fields that reference Account records
    default_account_fields = [
        "default_bank_account", "default_cash_account",
        "default_receivable_account", "default_payable_account",
        "default_expense_account", "default_income_account",
        "round_off_account", "write_off_account",
        "exchange_gain_loss_account", "unrealized_exchange_gain_loss_account",
        "default_deferred_revenue_account", "default_deferred_expense_account",
        "cost_center", "default_finance_book",
        "depreciation_expense_account", "disposal_account",
        "accumulated_depreciation_account",
    ]
    update_fields = {}
    meta = frappe.get_meta("Company")
    for field in default_account_fields:
        if meta.has_field(field):
            update_fields[field] = None
    if update_fields:
        frappe.db.set_value("Company", company, update_fields, update_modified=False)

    # Direct SQL delete — bypasses NestedSet validation entirely
    frappe.db.sql("DELETE FROM `tabAccount` WHERE company = %s", company)
    frappe.db.commit()

    return result


def _read_xlsx():
    """Read the QBO Chart of Accounts XLSX from the site files directory."""
    site = frappe.local.site
    file_path = f"/home/frappe/frappe-bench/sites/{site}/public/files/DCR Chart of Accounts.xlsx"

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    rows = []
    for idx, row in enumerate(ws.iter_rows(min_row=5, values_only=True), start=5):
        acct_num = row[0]
        name = row[1]

        if not acct_num or not name:
            continue
        acct_num_str = str(acct_num).strip()
        if acct_num_str.upper() == "TOTAL":
            continue

        qbo_type = str(row[2]).strip() if row[2] else ""
        detail_type = str(row[3]).strip() if row[3] else ""

        rows.append({
            "account_number": acct_num_str,
            "name": str(name).strip(),
            "qbo_type": qbo_type,
            "detail_type": detail_type,
        })

    wb.close()
    return rows


def _find_account(account_name, company):
    """Look up the actual Account document name by account_name + company.

    ERPNext names accounts as '{number} - {name} - {abbr}' when account_number
    is set, or '{name} - {abbr}' when it's not. This function finds the actual
    name regardless of numbering.
    """
    return frappe.db.get_value(
        "Account",
        {"account_name": account_name, "company": company},
        "name",
    )


def _create_account(name, number, is_group, root_type, account_type,
                     parent_account, company, dry_run=False):
    """Create a single Account document if it doesn't already exist.

    parent_account should be the actual document name (looked up via _find_account)
    or None/empty string for root accounts.

    Returns tuple: (action, actual_name).
    """
    existing = _find_account(name, company)
    if existing:
        return ("skipped", existing)

    if dry_run:
        return ("created", name)

    try:
        doc_data = {
            "doctype": "Account",
            "account_name": name,
            "is_group": is_group,
            "root_type": root_type,
            "company": company,
        }
        if number:
            doc_data["account_number"] = number
        if account_type:
            doc_data["account_type"] = account_type
        if parent_account:
            doc_data["parent_account"] = parent_account

        # ERPNext restricts certain account_types to group accounts only
        group_only_types = {"Current Asset", "Fixed Asset", "Current Liability"}
        if not is_group and account_type in group_only_types:
            doc_data.pop("account_type", None)

        doc = frappe.get_doc(doc_data)
        doc.flags.ignore_permissions = True
        if not parent_account:
            doc.flags.ignore_mandatory = True
        doc.insert()
        return ("created", doc.name)
    except Exception as e:
        frappe.log_error(f"COA Import: Failed to create account {name}", str(e))
        return ("error", f"{name}: {str(e)}")


@frappe.whitelist()
def import_chart_of_accounts(company, dry_run=False, limit=0):
    """Import Chart of Accounts from QBO export XLSX into ERPNext.

    Call via browser console:
        frappe.call({
            method: "dcr.api.coa_import.import_chart_of_accounts",
            args: { company: "Dealer Capital Resources" },
            callback: r => console.log(r.message)
        })
    """
    dry_run = frappe.utils.cint(dry_run)
    limit = frappe.utils.cint(limit)

    abbr = frappe.db.get_value("Company", company, "abbr")
    if not abbr:
        frappe.throw(_("Company {0} not found or has no abbreviation").format(company))

    # ── Delete existing accounts ────────────────────────────────────
    delete_result = _delete_existing_accounts(company, dry_run=dry_run)

    summary = {
        "deleted_accounts": delete_result["deleted"],
        "delete_errors": delete_result["errors"],
        "created_roots": [],
        "created_groups": [],
        "created_accounts": [],
        "skipped": [],
        "errors": [],
    }

    created_count = 0

    def _track(action, name, category):
        nonlocal created_count
        if action == "created":
            summary[category].append(name)
            created_count += 1
        elif action == "skipped":
            summary["skipped"].append(name)
        elif action == "error":
            summary["errors"].append(name)

    def _maybe_commit():
        nonlocal created_count
        if not dry_run and created_count > 0 and created_count % 20 == 0:
            frappe.db.commit()

    # ── Pass 1: Root accounts (no parent_account) ────────────────────
    for root_type, info in ROOT_ACCOUNTS.items():
        action, name = _create_account(
            name=info["name"],
            number=info["number"],
            is_group=1,
            root_type=root_type,
            account_type=None,
            parent_account=None,
            company=company,
            dry_run=dry_run,
        )
        _track(action, name, "created_roots")
        _maybe_commit()

    # ── Pass 2a: Intermediate groups ───────────────────────────────────
    for group_name, info in INTERMEDIATE_GROUPS.items():
        root_type = info["root_type"]
        root_name = ROOT_ACCOUNTS[root_type]["name"]
        parent_account = _find_account(root_name, company)

        group_account_type = None
        for qbo_type, (rt, at, gn) in QBO_TYPE_MAP.items():
            if gn == group_name:
                group_account_type = at
                break

        action, name = _create_account(
            name=group_name,
            number=info["number"],
            is_group=1,
            root_type=root_type,
            account_type=group_account_type,
            parent_account=parent_account,
            company=company,
            dry_run=dry_run,
        )
        _track(action, name, "created_groups")
        _maybe_commit()

    # ── Read XLSX ──────────────────────────────────────────────────────
    rows = _read_xlsx()
    if limit:
        rows = rows[:limit]

    # Identify colon-parent names so we know which standalone accounts
    # need to be is_group=1
    colon_parents = set()
    for row in rows:
        if ":" in row["name"]:
            parent_part = row["name"].split(":")[0].strip()
            colon_parents.add(parent_part)

    # ── Pass 2b: Create colon-parent groups ────────────────────────────
    colon_parent_info = {}
    for row in rows:
        if ":" in row["name"]:
            parent_part = row["name"].split(":")[0].strip()
            if parent_part not in colon_parent_info:
                colon_parent_info[parent_part] = row["qbo_type"]

    standalone_names = set()
    for row in rows:
        if ":" not in row["name"]:
            standalone_names.add(row["name"])

    for parent_name, qbo_type in colon_parent_info.items():
        if parent_name in standalone_names:
            continue

        mapping = QBO_TYPE_MAP.get(qbo_type)
        if not mapping:
            summary["errors"].append(f"Unknown QBO type '{qbo_type}' for colon-parent '{parent_name}'")
            continue

        root_type, account_type, group_name = mapping

        if group_name is None:
            parent_account = _find_account(ROOT_ACCOUNTS[root_type]["name"], company)
        else:
            parent_account = _find_account(group_name, company)

        action, name = _create_account(
            name=parent_name,
            number=None,
            is_group=1,
            root_type=root_type,
            account_type=account_type,
            parent_account=parent_account,
            company=company,
            dry_run=dry_run,
        )
        _track(action, name, "created_groups")
        _maybe_commit()

    # ── Pass 3: Leaf accounts (and standalone colon-parents) ───────────
    for row in rows:
        acct_name = row["name"]
        acct_number = row["account_number"]
        qbo_type = row["qbo_type"]

        mapping = QBO_TYPE_MAP.get(qbo_type)
        if not mapping:
            summary["errors"].append(f"Unknown QBO type '{qbo_type}' for account '{acct_name}'")
            continue

        root_type, account_type, group_name = mapping

        if ":" in acct_name:
            parent_part, child_part = acct_name.split(":", 1)
            parent_part = parent_part.strip()
            child_part = child_part.strip()
            parent_account = _find_account(parent_part, company)

            action, name = _create_account(
                name=child_part,
                number=acct_number,
                is_group=0,
                root_type=root_type,
                account_type=account_type,
                parent_account=parent_account,
                company=company,
                dry_run=dry_run,
            )
            _track(action, name, "created_accounts")
        else:
            is_group = 1 if acct_name in colon_parents else 0

            if group_name is None:
                parent_account = _find_account(ROOT_ACCOUNTS[root_type]["name"], company)
            else:
                parent_account = _find_account(group_name, company)

            action, name = _create_account(
                name=acct_name,
                number=acct_number,
                is_group=is_group,
                root_type=root_type,
                account_type=account_type,
                parent_account=parent_account,
                company=company,
                dry_run=dry_run,
            )
            _track(action, name, "created_accounts")

        _maybe_commit()

    # Final commit and rebuild NestedSet tree
    if not dry_run:
        frappe.db.commit()
        rebuild_tree("Account", "parent_account")

    summary["total_created"] = (
        len(summary["created_roots"])
        + len(summary["created_groups"])
        + len(summary["created_accounts"])
    )
    summary["total_skipped"] = len(summary["skipped"])
    summary["total_errors"] = len(summary["errors"])

    return summary
