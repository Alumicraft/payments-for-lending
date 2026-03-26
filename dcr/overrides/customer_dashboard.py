from frappe import _


def get_data(data):
    data["transactions"].append({
        "label": _("DCR"),
        "items": ["Factory Assignment", "MIFA", "Home Build Request"]
    })
    return data
