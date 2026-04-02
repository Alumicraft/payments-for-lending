app_name = "dcr"
app_title = "DCR"
app_publisher = "DCR"
app_description = "Dealer Capital Resources — Home Builder Lending Platform"
app_email = "hello@example.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext", "lending"]

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
                "Loan Application-repayment_amount-default",
                "Loan Application-total_payable_amount-default",
                "Loan Application-total_payable_interest-default",
            ]]
        ]
    },
]

# Include JS in doctype views
doctype_js = {
    "Loan": "public/js/loan.js",
    "Loan Application": "public/js/loan_application.js",
    "Customer": "public/js/customer.js",
    "Home Build Request": "public/js/home_build_request.js",
    "MIFA": "public/js/mifa.js",
    "Factory Assignment": "public/js/factory_assignment.js",
}

# Document Events
doc_events = {
    "Loan Application": {
        "validate": "dcr.api.lending.validate_loan_application"
    },
    "Loan": {
        "validate": "dcr.api.lending.on_loan_validate",
        "after_insert": "dcr.api.lending.on_loan_after_insert",
        "on_update": "dcr.api.lending.on_loan_on_update"
    },
    "Loan Disbursement": {
        "validate": "dcr.api.lending.on_loan_disbursement_validate"
    },
    "Bank Account": {
        "validate": "dcr.api.bank_account_ach.validate_single_default"
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
