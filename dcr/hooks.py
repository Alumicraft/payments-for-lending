app_name = "dcr"
app_title = "DCR"
app_publisher = "DCR"
app_description = "Dealer Capital Resources — Home Builder Lending Platform"
app_email = "hello@example.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext", "lending"]

boot_session = "dcr.api.boot.boot_session"

# Frappe Cloud serves /assets files with a long immutable browser cache.
# Keep these explicit URLs versioned so deployed client fixes are fetched
# without requiring users to hard-refresh stale browser caches.
DCR_ASSET_VERSION = "20260525-7"


def versioned_asset(path):
    return f"{path}?v={DCR_ASSET_VERSION}"


def versioned_doctype_asset(path):
    return f"{path}?v={DCR_ASSET_VERSION}"


app_include_js = [
    versioned_asset("/assets/dcr/js/icon_fix.js"),
    versioned_asset("/assets/dcr/js/sidebar_fix.js"),
    # Preconnects to Mapbox CDN, preloads icon assets, lazy-loads
    # mapbox-gl.js, and prefetches the map API responses on idle.
    versioned_asset("/assets/dcr/js/map_warmup.js"),
]
app_include_css = [
    versioned_asset("/assets/dcr/css/workspace_fullwidth.css"),
    versioned_asset("/assets/dcr/css/map.css"),
    versioned_asset("/assets/dcr/css/dcr_workspace.css"),
]

override_whitelisted_methods = {
    "frappe.desk.doctype.desktop_layout.desktop_layout.get_layout": "dcr.api.boot.get_layout_with_icons",
    "frappe.desk.doctype.workspace.workspace.save_page": "dcr.api.workspace.save_page",
}

after_install = "dcr.setup.after_install"
after_migrate = "dcr.setup.after_install"

# Fixtures — Property Setters only (standard field behavior).
# Custom fields are managed directly on Frappe Cloud Customize Form.
fixtures = [
    {
        "doctype": "Property Setter",
        "filters": [
            ["name", "in", [
                "Customer-first_name-hidden",
                "Customer-last_name-hidden",
                "Loan Application-applicant_type-hidden",
                "Loan Application-applicant_type-default",
                "Loan Application-is_term_loan-hidden",
                "Loan Application-is_secured_loan-hidden",
                "Loan Application-description-hidden",
                "Loan Application-proposed_pledges-hidden",
                "Loan Application-maximum_loan_amount-hidden",
                "Loan Application-repayment_method-hidden",
                "Loan Application-repayment_method-default",
                "Loan Application-repayment_periods-hidden",
                "Loan Application-repayment_periods-default",
                "Loan Application-rate_of_interest-read_only",
                "Loan Application-repayment_amount-read_only",
                "Loan Application-total_payable_amount-read_only",
                "Loan Application-total_payable_interest-read_only",
                "Loan Application-loan_amount-fetch_from",
                "Loan Application-loan_product-fetch_from",
                "Loan Application-rate_of_interest-fetch_from",
                "Loan Application-rate_of_interest-default",
                "Loan Application-repayment_amount-placeholder",
                "Loan Application-total_payable_amount-placeholder",
                "Loan Application-total_payable_interest-placeholder",
                "Loan Application-buyer_name-fetch_from",
                "Loan Application-applicant_email_address-fetch_from",
                "Loan Application-applicant_phone_number-fetch_from",
                "Loan Application-dcr_documents_section-depends_on",
                "Loan Application-signed_packet-placeholder",
                "Loan Application-applicant_email_address-read_only",
                "Loan Application-applicant_phone_number-read_only",
            ]]
        ]
    },
]

# Include JS in doctype views
doctype_js = {
    "Loan": "public/js/loan.js",
    "Loan Application": versioned_doctype_asset("public/js/loan_application.js"),
    "Customer": "public/js/customer.js",
    "Home Build Request": "public/js/home_build_request.js",
    "MIFA": "public/js/mifa.js",
    "Factory Assignment": "public/js/factory_assignment.js",
    "Loan Disbursement": "public/js/loan_disbursement.js",
    "Purchase Order": "public/js/hbr_connection_defaults.js",
    "Purchase Invoice": "public/js/hbr_connection_defaults.js",
    "Purchase Receipt": "public/js/hbr_connection_defaults.js",
    "Payment Entry": "public/js/hbr_connection_defaults.js",
    "Signature Request": "public/js/hbr_connection_defaults.js",
}

# Document Events
doc_events = {
    "Loan Application": {
        "validate": "dcr.api.lending.validate_loan_application",
        "on_update": "dcr.api.hbr_stage.sync_from_doc",
    },
    "Loan": {
        "validate": "dcr.api.lending.on_loan_validate",
        "after_insert": "dcr.api.lending.on_loan_after_insert",
        "on_update": "dcr.api.lending.on_loan_on_update",
        "on_update_after_submit": "dcr.api.hbr_stage.sync_from_doc",
    },
    "Loan Disbursement": {
        "validate": "dcr.api.lending.on_loan_disbursement_validate",
        "on_submit": "dcr.api.hbr_stage.sync_from_doc",
        "on_cancel": "dcr.api.hbr_stage.sync_from_doc",
    },
    "Purchase Order": {
        "on_submit": "dcr.api.hbr_stage.sync_from_doc",
        "on_cancel": "dcr.api.hbr_stage.sync_from_doc",
    },
    "Purchase Receipt": {
        "on_submit": "dcr.api.hbr_stage.sync_from_doc",
        "on_cancel": "dcr.api.hbr_stage.sync_from_doc",
    },
    "Bank Account": {
        "validate": "dcr.api.bank_account_ach.validate_single_default"
    },
    "Supplier": {
        "on_update": "dcr.api.map.geocode_supplier",
    },
    "Address": {
        "on_update": "dcr.api.map.geocode_address_suppliers",
    },
}

# Whitelisted Methods
# ------------------
# Methods accessible via /api/method/dcr.api.<module>.<method>

override_doctype_dashboards = {
    "Customer": "dcr.overrides.customer_dashboard.get_data"
}

override_doctype_class = {
    "Loan Repayment Schedule": "dcr.overrides.loan_repayment_schedule.CustomLoanRepaymentSchedule",
}

# Scheduled Tasks
scheduler_events = {
    "daily": [
        "dcr.tasks.scheduled_debits.process_upcoming_payments",
        "dcr.tasks.scheduled_debits.initiate_scheduled_transactions",
        "dcr.tasks.scheduled_debits.process_retry_transactions"
    ],
    "hourly": [
        "dcr.tasks.scheduled_debits.check_pending_transactions"
    ],
}

# Website Route Rules
website_route_rules = [
    {"from_route": "/plaid-setup", "to_route": "plaid_setup"},
    {"from_route": "/docusign-complete", "to_route": "docusign_complete"},
]
