/**
 * Populate Customize Form fetch_from fields when a doc is opened from an
 * HBR dashboard connection "+" button.
 */

(function() {
    var HBR_LINK_FIELDS = {
        "Purchase Order": "custom_home_build_request",
        "Purchase Invoice": "home_build_request",
        "Purchase Receipt": "custom_home_build_request",
        "Payment Entry": "custom_home_build_request"
    };

    frappe.ui.form.on("Signature Request", {
        onload: function(frm) {
            set_hbr_reference_doctype(frm);
        },
        reference_name: function(frm) {
            set_hbr_reference_doctype(frm);
        }
    });

    Object.keys(HBR_LINK_FIELDS).forEach(function(doctype) {
        var link_fieldname = HBR_LINK_FIELDS[doctype];
        var handlers = {
            onload: function(frm) {
                infer_hbr_reference(frm, link_fieldname).then(function() {
                    hydrate_hbr_fetch_fields(frm, link_fieldname);
                });
            }
        };
        handlers[link_fieldname] = function(frm) {
            hydrate_hbr_fetch_fields(frm, link_fieldname);
        };
        frappe.ui.form.on(doctype, handlers);
    });

    frappe.ui.form.on("Payment Entry", {
        refresh: function(frm) {
            recompute_selected_outstanding(frm);
        },
        references_add: function(frm) {
            recompute_selected_outstanding(frm);
            infer_hbr_reference(frm, "custom_home_build_request");
        },
        references_remove: function(frm) {
            recompute_selected_outstanding(frm);
        }
    });

    frappe.ui.form.on("Payment Entry Reference", {
        reference_name: function(frm) {
            infer_hbr_reference(frm, "custom_home_build_request");
        },
        outstanding_amount: function(frm) {
            recompute_selected_outstanding(frm);
        },
        allocated_amount: function(frm) {
            recompute_selected_outstanding(frm);
        }
    });

    function infer_hbr_reference(frm, link_fieldname) {
        if (!frm.is_new() || frm.doc[link_fieldname]) return Promise.resolve();

        if (frm.doc.doctype === "Purchase Invoice") {
            return infer_purchase_invoice_hbr(frm, link_fieldname);
        }
        if (frm.doc.doctype === "Payment Entry") {
            return infer_payment_entry_hbr(frm, link_fieldname);
        }
        return Promise.resolve();
    }

    function infer_purchase_invoice_hbr(frm, link_fieldname) {
        var item = (frm.doc.items || []).find(function(row) {
            return row.purchase_receipt || row.purchase_order;
        });
        if (!item) return Promise.resolve();

        if (item.purchase_receipt) {
            return frappe.db.get_value(
                "Purchase Receipt",
                item.purchase_receipt,
                ["custom_home_build_request"]
            ).then(function(result) {
                var hbr = result.message && result.message.custom_home_build_request;
                if (hbr) return frm.set_value(link_fieldname, hbr);
                if (item.purchase_order) {
                    return fetch_purchase_order_hbr(frm, link_fieldname, item.purchase_order);
                }
            });
        }
        return fetch_purchase_order_hbr(frm, link_fieldname, item.purchase_order);
    }

    function infer_payment_entry_hbr(frm, link_fieldname) {
        var reference = (frm.doc.references || []).find(function(row) {
            return row.reference_name && (
                row.reference_doctype === "Purchase Invoice" ||
                row.reference_doctype === "Purchase Order"
            );
        });
        if (!reference) return Promise.resolve();

        var fieldname = reference.reference_doctype === "Purchase Invoice"
            ? "home_build_request"
            : "custom_home_build_request";
        return frappe.db.get_value(
            reference.reference_doctype,
            reference.reference_name,
            [fieldname]
        ).then(function(result) {
            var hbr = result.message && result.message[fieldname];
            if (hbr) return frm.set_value(link_fieldname, hbr);
        });
    }

    function fetch_purchase_order_hbr(frm, link_fieldname, purchase_order) {
        if (!purchase_order) return Promise.resolve();
        return frappe.db.get_value(
            "Purchase Order",
            purchase_order,
            ["custom_home_build_request"]
        ).then(function(result) {
            var hbr = result.message && result.message.custom_home_build_request;
            if (hbr) return frm.set_value(link_fieldname, hbr);
        });
    }

    function recompute_selected_outstanding(frm) {
        if (!frm.fields_dict.custom_total_outstanding) return;

        var total = (frm.doc.references || []).reduce(function(sum, row) {
            return sum + flt(row.outstanding_amount);
        }, 0);
        if (flt(frm.doc.custom_total_outstanding) === total) return;

        if (frm.doc.docstatus === 0) {
            frm.set_value("custom_total_outstanding", total);
            return;
        }

        // Submitted Payment Entries are immutable. Refresh the calculated
        // display without marking the document dirty or exposing Update.
        frm.doc.custom_total_outstanding = total;
        frm.refresh_field("custom_total_outstanding");
    }

    function hydrate_hbr_fetch_fields(frm, link_fieldname) {
        var hbr_name = frm.doc[link_fieldname];
        if (!frm.is_new() || !hbr_name || frm.doc.__hbr_fetch_hydrated === hbr_name) return;
        frm.doc.__hbr_fetch_hydrated = hbr_name;

        frappe.db.get_doc("Home Build Request", hbr_name).then(function(hbr) {
            if (!hbr || !frappe.meta || !frappe.meta.get_docfields) return;
            var docfields = frappe.meta.get_docfields(frm.doc.doctype) || [];
            docfields.forEach(function(df) {
                if (!df.fetch_from || df.fetch_from.indexOf(link_fieldname + ".") !== 0) return;
                if (frm.doc[df.fieldname]) return;

                var source_field = df.fetch_from.slice(link_fieldname.length + 1);
                if (hbr[source_field] === undefined || hbr[source_field] === null || hbr[source_field] === "") return;
                frm.set_value(df.fieldname, hbr[source_field]);
            });
        });
    }

    function set_hbr_reference_doctype(frm) {
        if (!frm.is_new() || frm.doc.reference_doctype || !frm.doc.reference_name) return;
        if (!/^ACC-HBR-\d{4}-\d+$/.test(frm.doc.reference_name)) return;
        frm.set_value("reference_doctype", "Home Build Request");
    }
})();
