import frappe


def execute():
    """Reorder Customer DocType links so DCR items appear in the right sections.

    Target order for Pre Sales: Opportunity, Factory Assignment, MIFA, Quotation
    Target order for Orders: Home Build Request, Sales Order, Delivery Note, Sales Invoice
    """
    # Get all existing links for Customer
    links = frappe.get_all(
        "DocType Link",
        filters={"parent": "Customer", "parenttype": "DocType"},
        fields=["name", "link_doctype", "group"],
        order_by="idx asc"
    )

    if not links:
        return

    # Define the desired order by group
    group_order = {
        "Pre Sales": ["Opportunity", "Factory Assignment", "MIFA", "Quotation"],
        "Orders": ["Home Build Request", "Sales Order", "Delivery Note", "Sales Invoice"],
    }

    # Build ordered list: first place items with explicit ordering, then the rest
    ordered = []
    handled = set()

    # Process groups with explicit ordering first
    for group, doctype_order in group_order.items():
        group_links = [l for l in links if l.get("group") == group]
        # Sort by desired order
        for dt in doctype_order:
            for l in group_links:
                if l["link_doctype"] == dt:
                    ordered.append(l)
                    handled.add(l["name"])
                    break
        # Add any remaining in this group not in our explicit order
        for l in group_links:
            if l["name"] not in handled:
                ordered.append(l)
                handled.add(l["name"])

    # Add remaining links (other groups) in their original order
    for l in links:
        if l["name"] not in handled:
            ordered.append(l)

    # Update idx values
    for i, link in enumerate(ordered, start=1):
        frappe.db.set_value("DocType Link", link["name"], "idx", i, update_modified=False)

    frappe.db.commit()
