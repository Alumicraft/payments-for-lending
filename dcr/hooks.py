app_name = "dcr"
app_title = "DCR"
app_publisher = "DCR"
app_description = "Dealer Capital Resources — Home Builder Lending Platform"
app_email = "hello@example.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext", "lending"]

# Fixtures - custom fields synced on bench migrate
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["name", "in", [
                "Customer-dealer_information_section",
                "Customer-dealer_license_no",
                "Customer-license_expiry_date",
                "Customer-sellers_permit_no",
                "Customer-column_break_dealer1",
                "Customer-w9_status",
                "Customer-mifa_required",
                "Customer-dealer_agreement_status",
                "Customer-master_dealer_list_updated",
                "Customer-dcr_application_section",
                "Customer-dcr_application_status",
                "Customer-dcr_account_no",
                "Customer-column_break_dcr1",
                "Customer-dealer_license_copy",
                "Customer-sellers_permit_copy",
                "Customer-w9_copy",
                "Customer-retailer_application_copy",
                "Supplier-lead_time_section",
                "Supplier-standard_lead_time_days",
                "Supplier-current_lead_time_days",
                "Supplier Quotation-home_build_request",
                "Supplier Quotation-plot_plan",
                "Supplier Quotation-signed_by_dealer",
                "Supplier Quotation-signature_date",
                "Sales Order-home_build_request",
                "Sales Order-home_type",
                "Sales Order-financing_type",
                "Sales Order-property_type",
                "Loan Application-home_build_request",
                "Loan Application-home_type",
                "Loan Application-dcr_lending_section",
                "Loan Application-requested_advance_amount",
                "Loan Application-advance_date_requested",
                "Loan Application-column_break_dcr_lending",
                "Loan Application-outstanding_loan_balance",
                "Loan Application-available_credit",
                "Loan Application-signed_packet",
                "Loan Application-dcr_documents_section",
                "Loan Application-doc_checklist",
                "Loan-ach_payment_section",
                "Loan-ach_payment_account",
                "Loan Disbursement-home_build_request",
                "Loan Disbursement-factory_po",
                "Loan Disbursement-factory",
            ]]
        ]
    }
]

# Include JS in doctype views
doctype_js = {
    "Loan": "public/js/loan.js",
    "Customer": "public/js/customer.js",
    "Home Build Request": "public/js/home_build_request.js",
}

# Document Events
doc_events = {
    "Customer": {
        "on_update": "dcr.api.adobesign.on_customer_update"
    },
    "Loan Application": {
        "validate": "dcr.api.lending.validate_loan_application"
    },
}

# Whitelisted Methods
# ------------------
# Methods accessible via /api/method/dcr.api.<module>.<method>

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
