import frappe


def after_install():
    """Ensure DCR module definition and required groups exist."""
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

    reorder_loan_application_fields()

    frappe.db.commit()


def reorder_loan_application_fields():
    """Reorder ALL Loan Application fields into the definitive spec order.

    Uses Customize Form API so the order is enforced every deploy,
    regardless of how fixture sync placed things.

    Also hides standard section/column breaks that are no longer needed
    (safe to do here because their children have been moved to custom sections).
    """
    # Definitive field order — every field on the form, in exact spec order.
    # Visible fields first, then hidden standard fields at the end.
    FIELD_ORDER = [
        # --- Section 1: Header (no label) ---
        "applicant_type",        # standard, hidden, default "Customer"
        "applicant",             # standard
        "applicant_name",        # standard
        "column_break_header",   # custom (NEW)
        "posting_date",          # standard
        "status",                # standard

        # --- Section 2: Deal reference ---
        "deal_reference_section",  # custom
        "home_build_request",      # custom
        "home_type",               # custom
        "column_break_deal_ref",   # custom
        "factory",                 # custom

        # --- Section 3: Lending ---
        "lending_section",         # custom (NEW, replaces dcr_lending_section)
        "loan_product",            # standard
        "loan_amount",             # standard
        "advance_date_requested",  # custom
        "home_serial_no",          # custom
        "quote_no",                # custom
        "floor_plan",              # custom (label: Model)
        "column_break_lending",    # custom (NEW)
        "rate_of_interest",        # standard, read_only
        "buyer_name",              # custom (label: Buyer Name)

        # --- Section 4: Lending calculations ---
        "lending_calculations_section",  # custom (NEW)
        "available_credit",              # custom
        "outstanding_loan_balance",      # custom
        "custom_current_yn",             # custom (label: Current)
        "column_break_lending_calc",     # custom (NEW)
        "monthly_interest_amount",       # custom, read_only
        "monthly_insurance_amount",      # custom
        "repayment_amount",              # standard, read_only
        "total_payable_amount",          # standard, read_only
        "total_payable_interest",        # standard, read_only

        # --- Section 5: Pre-approval letter ---
        "advance_preapproval_section",   # custom (label: Pre-approval letter)
        "custom_projected_sales_price",  # custom
        "custom_projected_equity",       # custom, read_only
        "custom_projected_ltv",          # custom, read_only
        "custom_projected_payoff",       # custom
        "column_break_preapproval",      # custom
        "custom_monthly_space_rent",     # custom, read_only
        "custom_notes",                  # custom

        # --- Section 6: Signed documents ---
        "dcr_documents_section",  # custom (NEW)
        "signed_packet",          # custom, read_only

        # --- Section 7: Repayment info ---
        "repayment_info",          # standard section
        "repayment_method",        # standard, hidden, default
        "column_break_repayment",  # custom (NEW)
        "repayment_periods",       # standard, hidden, default
        "company",                 # standard

        # --- Hidden standard fields (parked at end) ---
        "column_break_2",
        "section_break_4",
        "is_term_loan",
        "loan_security_details_section",
        "is_secured_loan",
        "column_break_7",
        "description",
        "proposed_pledges",
        "maximum_loan_amount",
        "column_break_11",
        "amended_from",
    ]

    # Standard section/column breaks to hide (only safe after reorder)
    HIDE_FIELDS = [
        "section_break_4",
        "column_break_2",
        "column_break_7",
        "loan_security_details_section",
        "column_break_11",
    ]

    # Clear stale link_filters BEFORE Customize Form reads it
    frappe.db.sql("""
        UPDATE `tabCustom Field`
        SET link_filters = NULL
        WHERE name = 'Loan Application-home_build_request'
        AND link_filters IS NOT NULL
    """)

    customize = frappe.get_doc("Customize Form")
    customize.doc_type = "Loan Application"
    customize.fetch_to_customize()

    # Build lookup: fieldname → field row
    field_map = {f.fieldname: f for f in customize.fields}

    # Skip fields not yet on the form (user may not have created them yet)
    missing = [fn for fn in FIELD_ORDER if fn not in field_map]
    if missing:
        print(f"  NOTE: LA reorder skipping missing fields: {missing}")

    # Reorder: place known spec fields first, then any unexpected fields at the end
    ordered = [field_map[fn] for fn in FIELD_ORDER if fn in field_map]
    remaining = [f for f in customize.fields if f.fieldname not in set(FIELD_ORDER)]
    if remaining:
        print(f"  WARNING: unexpected fields on LA (appended at end): "
              f"{[f.fieldname for f in remaining]}")

    customize.fields = ordered + remaining

    # Reassign idx values (1-based)
    for i, field in enumerate(customize.fields):
        field.idx = i + 1

    # Hide standard section/column breaks (now safe — their children moved away)
    for fn in HIDE_FIELDS:
        if fn in field_map:
            field_map[fn].hidden = 1

    try:
        customize.save_customization()
        print("  Loan Application field order updated successfully")
    except Exception as e:
        print(f"  ERROR: LA reorder failed — {e}")
        frappe.log_error("LA field reorder failed", str(e))
