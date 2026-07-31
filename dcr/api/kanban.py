"""Protect backend-derived HBR Kanban columns from manual edits."""

import frappe
from frappe import _


def _is_hbr_board(board_name):
    return (
        frappe.db.get_value("Kanban Board", board_name, "reference_doctype")
        == "Home Build Request"
    )


def _derived_stage_error():
    frappe.throw(
        _("Home Build Request order stages are updated automatically from purchase and delivery records.")
    )


@frappe.whitelist()
def update_order(board_name, order):
    if _is_hbr_board(board_name):
        return frappe.get_doc("Kanban Board", board_name), []

    from frappe.desk.doctype.kanban_board.kanban_board import update_order as framework_update_order

    return framework_update_order(board_name, order)


@frappe.whitelist()
def update_order_for_single_card(
    board_name,
    docname,
    from_colname,
    to_colname,
    old_index,
    new_index,
):
    if _is_hbr_board(board_name):
        _derived_stage_error()

    from frappe.desk.doctype.kanban_board.kanban_board import (
        update_order_for_single_card as framework_update_single,
    )

    return framework_update_single(
        board_name,
        docname,
        from_colname,
        to_colname,
        old_index,
        new_index,
    )


@frappe.whitelist()
def add_column(board_name, column_title):
    if _is_hbr_board(board_name):
        _derived_stage_error()

    from frappe.desk.doctype.kanban_board.kanban_board import add_column as framework_add_column

    return framework_add_column(board_name, column_title)


@frappe.whitelist()
def archive_restore_column(board_name, column_title, status):
    if _is_hbr_board(board_name):
        _derived_stage_error()

    from frappe.desk.doctype.kanban_board.kanban_board import (
        archive_restore_column as framework_archive_restore,
    )

    return framework_archive_restore(board_name, column_title, status)


@frappe.whitelist()
def update_column_order(board_name, order):
    if _is_hbr_board(board_name):
        _derived_stage_error()

    from frappe.desk.doctype.kanban_board.kanban_board import (
        update_column_order as framework_update_columns,
    )

    return framework_update_columns(board_name, order)
