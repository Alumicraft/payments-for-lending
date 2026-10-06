"""Scoped adapters for the native Frappe dealer HBR Web Form.

Rendering and saving stay on Frappe's Web Form path. DCR supplies its existing
Customer ownership and review rules without granting broad native DocPerms.
"""

import json

import frappe

from dcr.api import dealer_portal as portal


FORM_NAME = "dealer-home-build-request"
FORM_ROUTE = "dealer-home-request"
DOCTYPE = "Home Build Request"
FIELD_PROPERTIES = (
    "fieldname", "fieldtype", "label", "options", "reqd", "depends_on",
    "mandatory_depends_on", "read_only_depends_on", "description", "default",
    "precision", "placeholder", "max_length", "read_only", "hidden",
)


def require_form(form=None, request_key=None):
    form = form or frappe.get_doc("Web Form", FORM_NAME)
    if (form.name != FORM_NAME or form.doc_type != DOCTYPE or not form.published
            or not form.login_required or form.anonymous or request_key):
        portal._deny("This dealer form is not available. Please return to your dashboard.")
    return form


def build_fields(meta, factories=None):
    """Use current DocType metadata, exposing only the dealer input allowlist.

    Empty staff-only sections/columns are discarded. Factory is a bounded
    Autocomplete rather than a general Supplier lookup. Native dependencies and
    validation controls remain intact for the other fields.
    """
    sections = []
    section = []
    for df in meta.fields:
        fieldtype = portal._value(df, "fieldtype")
        fieldname = portal._value(df, "fieldname")
        if fieldtype == "Section Break":
            sections.append(section)
            section = [df]
        elif fieldtype == "Column Break" or fieldname in portal.HBR_INPUT_FIELDS:
            section.append(df)
    sections.append(section)

    result = []
    for section in sections:
        if not any(portal._value(df, "fieldname") in portal.HBR_INPUT_FIELDS for df in section):
            continue
        section_fields = []
        column_has_input = False
        for df in section:
            field = {key: portal._value(df, key) for key in FIELD_PROPERTIES
                     if portal._value(df, key) is not None}
            if field.get("label"):
                # Scoped presentation labels; the DocType's metadata and native
                # field/dependency/validation identities remain unchanged.
                label = field["label"]
                field["label"] = {"Serial No": "Serial number", "Factory Quote No": "Factory quote number", "Space No": "Space number"}.get(
                    label, label if label.isupper() else label[:1] + label[1:].lower())
            if field["fieldtype"] == "Column Break":
                if not column_has_input:
                    continue
                column_has_input = False
            elif field["fieldtype"] != "Section Break":
                column_has_input = True
                if field["fieldname"] == "factory":
                    choices = factories or []
                    field.update(fieldtype="Autocomplete", options=json.dumps([
                        {"value": item["name"], "label": item.get("label") or item["name"]}
                        for item in choices
                    ]), default=choices[0]["name"] if len(choices) == 1 else "")
                    field["description"] = "Choose one of your assigned factories." if choices else "No factories are assigned to your dealer account yet."
                    if not choices:
                        field["read_only"] = 1
            section_fields.append(field)
        while section_fields and section_fields[-1]["fieldtype"] == "Column Break":
            section_fields.pop()
        result.extend(section_fields)
    return result


def reference_values(hbr):
    """Never serialize staff fields or child-table controls into the Web Form."""
    return {
        "name": portal._value(hbr, "name"),
        "doctype": DOCTYPE,
        "modified": portal._json_value(portal._value(hbr, "modified")),
        **{field: portal._json_value(portal._value(hbr, field))
           for field in portal.HBR_INPUT_FIELDS},
    }


def configure_fields(form, customer):
    form.set("web_form_fields", build_fields(
        frappe.get_meta(DOCTYPE), portal._get_factories(customer)))


@frappe.whitelist(allow_guest=True, methods=["POST", "PUT"])
def accept(web_form, data, web_form_request_key=None, **kwargs):
    if web_form != FORM_NAME:
        from frappe.website.doctype.web_form.web_form import accept as native_accept
        return native_accept(web_form, data, web_form_request_key)

    require_form(request_key=web_form_request_key)
    portal.get_current_dealer_customer()
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            portal._deny("The home request data is invalid.")
    if not isinstance(data, dict):
        portal._deny("The home request data is invalid.")
    if data.get("doctype", DOCTYPE) != DOCTYPE or data.get("web_form_name", FORM_NAME) != FORM_NAME:
        portal._deny("The home request data is invalid.")
    if set(data) - portal.HBR_INPUT_FIELDS - {"name", "doctype", "web_form_name", "modified"}:
        portal._deny("The home request contains an unsupported field.")
    payload = {key: value for key, value in data.items() if key in portal.HBR_INPUT_FIELDS}
    result = portal.save_hbr_draft(
        payload=payload, name=data.get("name"), expected_modified=data.get("modified"))
    # Native Web Form only needs the saved name to finish and navigate. Do not
    # return a full Document, which would expose DCR's internal fields.
    return {"name": result["name"], "doctype": DOCTYPE}


@frappe.whitelist(allow_guest=True)
def get_form_data(doctype, docname=None, web_form_name=None, web_form_request_key=None):
    if web_form_name != FORM_NAME:
        from frappe.website.doctype.web_form.web_form import get_form_data as native_get_form_data
        return native_get_form_data(doctype, docname, web_form_name, web_form_request_key)

    form = require_form(request_key=web_form_request_key)
    customer = portal.get_current_dealer_customer()
    if doctype != DOCTYPE:
        portal._deny("That document is not available in this dealer form.")
    configure_fields(form, customer)
    out = {"web_form": form.as_dict()}
    if docname:
        out["doc"] = reference_values(portal._get_owned_hbr(docname, customer))
    return out
