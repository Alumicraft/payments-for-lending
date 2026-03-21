app_name = "dcr"
app_title = "DCR"
app_publisher = "DCR"
app_description = "Dealer Capital Resources — Home Builder Lending Platform"
app_email = "hello@example.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext", "lending"]

after_install = "dcr.setup.after_install"
after_migrate = "dcr.setup.after_install"

# Fixtures - custom fields synced on bench migrate
fixtures = [
    {
        "doctype": "DocType Link",
        "filters": [
            ["name", "in", [
                "Customer-Home Build Request",
                "Customer-MIFA",
                "Customer-Factory Assignment",
                "Loan Application-Signature Request",
                "Sales Order-Home Build Request",
            ]]
        ]
    },
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
                "Loan-home_deal_reference_section",
                "Loan-home_serial_no",
                "Loan-buyer_name",
                "Loan-column_break_home_deal",
                "Loan-factory",
                "Loan-payoff_section",
                "Loan-payoff_date",
                "Loan-payoff_good_thru_date",
                "Loan-column_break_payoff1",
                "Loan-interest_owed_at_payoff",
                "Loan-late_fees_collected",
                "Loan-service_fee_amount",
                "Loan-insurance_at_payoff",
                "Loan-column_break_payoff2",
                "Loan-principal_collected",
                "Loan-paid_from_escrow",
                "Loan-rebate_section",
                "Loan-qualifying_amount",
                "Loan-rebate_percentage",
                "Loan Disbursement-home_build_request",
                "Loan Disbursement-factory_po",
                "Loan Disbursement-factory",
                "Loan Application-exhibit_a_section",
                "Loan Application-home_serial_no",
                "Loan Application-quote_no",
                "Loan Application-floor_plan",
                "Loan Application-column_break_exhibit_a",
                "Loan Application-buyer_name",
                "Loan Application-monthly_interest_amount",
                "Loan Application-monthly_insurance_amount",
                "Loan Application-first_autopay_description",
                "Loan Application-advance_preapproval_section",
                "Loan Application-custom_current_yn",
                "Loan Application-custom_projected_investment",
                "Loan Application-custom_projected_sales_price",
                "Loan Application-column_break_preapproval",
                "Loan Application-custom_projected_equity",
                "Loan Application-custom_projected_ltv",
                "Loan Application-custom_monthly_space_rent",
                "Loan Application-custom_projected_payoff",
                "Loan Application-custom_notes",
                "Customer-dealer_agreement_section",
                "Customer-rebate_percentage",
                "Customer-entity_type",
            ]]
        ]
    }
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
    "Sales Order": {
        "on_submit": "dcr.api.sales_order_hooks.on_submit"
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
