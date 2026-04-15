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
        """Submission locks the deal record. Downstream docs created manually."""
        pass

    def validate_checklist_complete(self):
        """Block submission unless every checklist row has an attachment or is waived."""
        incomplete = []
        for row in self.doc_checklist:
            if not row.waived and not row.attachment:
                incomplete.append(row.document_type)

        if incomplete:
            frappe.throw(
                _("The following documents are missing: {0}").format(
                    ", ".join(incomplete)
                ),
                title=_("Document checklist incomplete"),
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

