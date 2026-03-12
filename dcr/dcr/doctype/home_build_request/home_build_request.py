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
    ("Spec", "DCR Floored", "Park"): [
        "Spec Info Sheet", "Storage Agreement", "Park Agreement",
        "Factory Quote", "Plot Plan"
    ],
    ("Spec", "DCR Floored", "Private Property"): [
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
    ("Customer Sold", "DCR Floored", "Park"): [
        "Retail Sold Info Sheet", "Purchase Contract", "Escrow Proof",
        "Factory Quote", "Plot Plan", "Loan Approval", "Park Approval",
        "Insurance"
    ],
    ("Customer Sold", "DCR Floored", "Private Property"): [
        "Retail Sold Info Sheet", "Purchase Contract", "Escrow Proof",
        "Factory Quote", "Plot Plan"
    ],
}


class HomeBuildRequest(Document):
    def validate(self):
        if self.financing_type == "DCR Floored" and not self.property_type:
            frappe.throw(_("Property Type is required"))

    def before_submit(self):
        self.validate_checklist_complete()

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
