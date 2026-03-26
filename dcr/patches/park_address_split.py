import frappe


def execute():
    """Migrate Park address/city_state_zip to split fields."""
    frappe.reload_doc("dcr", "doctype", "park")
    parks = frappe.get_all("Park", fields=["name", "address", "city_state_zip"])

    for park in parks:
        updates = {}
        if park.get("address"):
            updates["address_line1"] = park.address

        csz = park.get("city_state_zip") or ""
        if csz.strip():
            try:
                if "," in csz:
                    city_part, remainder = csz.rsplit(",", 1)
                    updates["city"] = city_part.strip()
                    tokens = remainder.strip().split()
                    if len(tokens) >= 2:
                        updates["zip"] = tokens[-1]
                        updates["state"] = " ".join(tokens[:-1])
                    elif len(tokens) == 1:
                        updates["state"] = tokens[0]
                else:
                    tokens = csz.strip().split()
                    if len(tokens) >= 3:
                        updates["zip"] = tokens[-1]
                        updates["state"] = tokens[-2]
                        updates["city"] = " ".join(tokens[:-2])
                    else:
                        frappe.log_error(
                            f"Park {park.name}: unparseable city_state_zip '{csz}'",
                            "Park Address Migration"
                        )
            except Exception:
                frappe.log_error(
                    f"Park {park.name}: failed to parse '{csz}'",
                    "Park Address Migration"
                )

        if updates:
            frappe.db.set_value("Park", park.name, updates, update_modified=False)

    frappe.db.commit()
