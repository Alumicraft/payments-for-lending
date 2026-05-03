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

    Object.keys(HBR_LINK_FIELDS).forEach(function(doctype) {
        var link_fieldname = HBR_LINK_FIELDS[doctype];
        var handlers = {
            onload: function(frm) {
                hydrate_hbr_fetch_fields(frm, link_fieldname);
            }
        };
        handlers[link_fieldname] = function(frm) {
            hydrate_hbr_fetch_fields(frm, link_fieldname);
        };
        frappe.ui.form.on(doctype, handlers);
    });

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
})();
