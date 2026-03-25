import frappe
from frappe import _
from frappe.model.document import Document


# Document requirements lookup keyed by (home_type, financing_type, property_type)
DOC_REQUIREMENTS = {
    ("Spec", "Cash", "Park"): [
        "Spec Info Sheet", "Storage Agreement", "Park Agreement",
        "Factory Quote", "Plot Plan"
    ],
    ("Spec", "Cash", "Private Property"): [
        "Spec Info Sheet", "Factory Quote", "Plot Plan", "50% Deposit Proof"
    ],
    ("Spec", "Floored", "Park"): [
        "Spec Info Sheet", "Storage Agreement", "Park Agreement",
        "Factory Quote", "Plot Plan"
    ],
    ("Spec", "Floored", "Private Property"): [
        "Spec Info Sheet", "Factory Quote", "Plot Plan", "50% Deposit Proof"
    ],
    ("Customer Sold", "Cash", "Park"): [
        "Retail Sold Info Sheet", "Purchase Contract", "Escrow Proof",
        "Factory Quote", "Plot Plan", "Loan Approval", "Park Approval",
        "Insurance"
    ],
    ("Customer Sold", "Cash", "Private Property"): [
        "Cash Private Info Sheet", "Purchase Contract", "Escrow Proof",
        "Factory Quote", "50% Deposit Proof"
    ],
    ("Customer Sold", "Floored", "Park"): [
        "Retail Sold Info Sheet", "Purchase Contract", "Escrow Proof",
        "Factory Quote", "Plot Plan", "Loan Approval", "Park Approval",
        "Insurance"
    ],
    ("Customer Sold", "Floored", "Private Property"): [
        "Retail Sold Info Sheet", "Purchase Contract", "Escrow Proof",
        "Factory Quote", "Plot Plan"
    ],
}


class HomeBuildRequest(Document):
    def validate(self):
        if self.financing_type == "Floored" and not self.property_type:
            frappe.throw(_("Property Type is required"))

        # Warn if factory has no approved Factory Assignment for this dealer
        if self.factory and self.customer:
            has_fa = frappe.db.exists("Factory Assignment", {
                "customer": self.customer,
                "factory": self.factory,
                "docstatus": 1,
                "active": 1
            })
            if not has_fa:
                frappe.msgprint(
                    _("Factory {0} has no approved Factory Assignment for dealer {1}.").format(
                        self.factory, self.customer
                    ),
                    indicator="orange",
                    title=_("Missing Factory Assignment")
                )

        # Enforce home_serial_no uniqueness (can't use DB unique because empty values conflict)
        if self.home_serial_no:
            existing = frappe.db.get_value(
                "Home Build Request",
                {"home_serial_no": self.home_serial_no, "name": ["!=", self.name]},
                "name"
            )
            if existing:
                frappe.throw(
                    _("Home Serial No {0} is already used on {1}.").format(
                        self.home_serial_no, existing
                    )
                )

    def before_submit(self):
        self.validate_checklist_complete()

    def on_submit(self):
        # Create Supplier Quotation for all deals (floored + cash)
        self._create_supplier_quotation()

        # Create Loan Application for Floored deals only
        if self.financing_type == "Floored":
            self._create_loan_application()

    def _create_supplier_quotation(self):
        """Auto-create Supplier Quotation from HBR on submit."""
        if not self.factory:
            frappe.msgprint(
                _("No factory assigned — Supplier Quotation not created."),
                indicator="orange"
            )
            return

        existing = frappe.db.exists("Supplier Quotation", {
            "home_build_request": self.name,
            "docstatus": ["!=", 2]
        })
        if existing:
            frappe.msgprint(
                _("Supplier Quotation {0} already exists for this Home Build Request.").format(existing),
                indicator="orange"
            )
            return

        item_code = "Manufactured Home"
        if not frappe.db.exists("Item", item_code):
            frappe.throw(
                _('Item "{0}" does not exist. Please create it first (non-stock service item).').format(
                    item_code
                )
            )

        sq = frappe.new_doc("Supplier Quotation")
        sq.supplier = self.factory
        sq.home_build_request = self.name
        sq.company = frappe.defaults.get_global_default("company")

        amount = self.home_invoice_plus_freight or 0
        sq.append("items", {
            "item_code": item_code,
            "qty": 1,
            "rate": amount,
            "amount": amount,
        })

        sq.insert()

        # Copy factory quote attachment from checklist if exists
        self._copy_factory_quote_to_sq(sq.name)

        # Link back
        self.db_set("factory_quote", sq.name)

        frappe.msgprint(
            _("Supplier Quotation {0} created.").format(
                f'<a href="/app/supplier-quotation/{sq.name}">{sq.name}</a>'
            ),
            indicator="green",
            alert=True,
        )

    def _copy_factory_quote_to_sq(self, sq_name):
        """Copy the Factory Quote attachment from the HBR checklist to the SQ."""
        for row in self.doc_checklist:
            if row.document_type == "Factory Quote" and row.attachment:
                try:
                    frappe.get_doc({
                        "doctype": "File",
                        "file_url": row.attachment,
                        "attached_to_doctype": "Supplier Quotation",
                        "attached_to_name": sq_name,
                    }).insert(ignore_permissions=True)
                except Exception:
                    frappe.log_error(
                        f"Failed to copy factory quote attachment to SQ {sq_name}",
                        "HBR Submit"
                    )
                break

    def _create_loan_application(self):
        """Auto-create Loan Application for Floored deals on HBR submit."""
        existing = frappe.db.exists("Loan Application", {
            "home_build_request": self.name,
            "docstatus": ["!=", 2]
        })
        if existing:
            frappe.msgprint(
                _("Loan Application {0} already exists for this Home Build Request.").format(existing),
                indicator="orange"
            )
            return

        la = frappe.new_doc("Loan Application")
        la.applicant_type = "Customer"
        la.applicant = self.customer
        la.home_build_request = self.name
        la.home_type = self.home_type
        if self.factory:
            la.factory = self.factory

        # Set loan product from customer default
        default_product = frappe.db.get_value("Customer", self.customer, "default_loan_product")
        if default_product:
            la.loan_product = default_product

        # Set loan amount from home invoice if available
        if self.home_invoice_plus_freight:
            la.loan_amount = self.home_invoice_plus_freight

        # Ensure repayment fields are set so lending validate doesn't fail
        if not la.repayment_method:
            la.repayment_method = "Repay Over Number of Periods"
        if not la.repayment_periods:
            la.repayment_periods = 12
        if not la.repayment_amount:
            la.repayment_amount = 0

        la.insert()

        # Link back
        self.loan_application = la.name
        self.db_set("loan_application", la.name)

        frappe.msgprint(
            _("Loan Application {0} created for flooring.").format(
                f'<a href="/app/loan-application/{la.name}">{la.name}</a>'
            ),
            indicator="green",
            alert=True,
        )

    def validate_checklist_complete(self):
        """Block submission until all required checklist items are Received or Verified."""
        incomplete = []
        for row in self.doc_checklist:
            if row.status not in ("Received", "Verified", "Waived"):
                incomplete.append(row.document_type)

        if incomplete:
            frappe.throw(
                _("The following documents are still pending: {0}").format(
                    ", ".join(incomplete)
                ),
                title=_("Document Checklist Incomplete")
            )


@frappe.whitelist()
def get_required_docs(home_type, financing_type, property_type):
    """Return list of required document types for a given combination.

    Called from client script on field change to auto-populate the
    Document Checklist child table.
    """
    key = (home_type, financing_type, property_type)
    docs = DOC_REQUIREMENTS.get(key, [])
    return docs


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_assigned_factories(doctype, txt, searchfield, start, page_len, filters):
    """Return factories where this customer has an approved Factory Assignment."""
    customer = filters.get("customer")
    if not customer:
        return []

    return frappe.db.sql("""
        SELECT DISTINCT fa.factory, fa.factory
        FROM `tabFactory Assignment` fa
        WHERE fa.customer = %(customer)s
            AND fa.docstatus = 1
            AND fa.active = 1
            AND fa.factory LIKE %(txt)s
        ORDER BY fa.factory
        LIMIT %(page_len)s OFFSET %(start)s
    """, {
        "customer": customer,
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })


@frappe.whitelist()
def create_loan_application_from_hbr(hbr_name):
    """Manual fallback to create Loan Application from a submitted HBR."""
    hbr = frappe.get_doc("Home Build Request", hbr_name)
    hbr.check_permission("write")
    if hbr.docstatus != 1:
        frappe.throw(_("Home Build Request must be submitted first."))
    if hbr.financing_type != "Floored":
        frappe.throw(_("Loan Applications are only created for Floored deals."))
    hbr._create_loan_application()
    return {"success": True}
