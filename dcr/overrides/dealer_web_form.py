"""Native Web Form rendering, narrowed only for DCR's dealer HBR form."""

import frappe
from frappe.website.doctype.web_form.web_form import WebForm

from dcr.api import dealer_portal as portal
from dcr.api import dealer_web_form as dealer_form


class DealerWebForm(WebForm):
    def get_context(self, context):
        if self.name != dealer_form.FORM_NAME:
            return super().get_context(context)
        dealer_form.require_form(self, frappe.form_dict.get("web_form_request_key"))
        if frappe.session.user in (None, "Guest", "guest"):
            frappe.local.flags.redirect_location = "/login?redirect-to=/dealer-home-request/new"
            raise frappe.Redirect
        customer = portal.get_current_dealer_customer()
        if frappe.form_dict.get("name"):
            hbr = portal._get_owned_hbr(frappe.form_dict.name, customer)
            if frappe.form_dict.get("is_edit"):
                portal._require_editable_hbr(hbr)
        dealer_form.configure_fields(self, customer)
        return super().get_context(context)

    def has_web_form_permission(self, doctype, name, ptype="read"):
        if self.name != dealer_form.FORM_NAME:
            return super().has_web_form_permission(doctype, name, ptype)
        dealer_form.require_form(self)
        if doctype != dealer_form.DOCTYPE or ptype not in {"read", "write"}:
            return False
        hbr = portal._get_owned_hbr(name)
        if ptype == "write":
            portal._require_editable_hbr(hbr)
        return True

    def get_web_form_request(self, key=None, **kwargs):
        if self.name != dealer_form.FORM_NAME:
            return super().get_web_form_request(key, **kwargs)
        dealer_form.require_form(self, key)
        return None

    def load_form_data(self, context, web_form_request=None):
        if self.name != dealer_form.FORM_NAME:
            return super().load_form_data(context, web_form_request)
        # Keep Frappe's native context and controls; sanitize before any HTML or
        # reference_doc JSON is rendered. This also covers staff-created HBRs
        # and multiple portal users on the same Dealer Customer.
        super().load_form_data(context, web_form_request)
        if frappe.form_dict.get("name"):
            context.reference_doc = dealer_form.reference_values(
                portal._get_owned_hbr(frappe.form_dict.name))
