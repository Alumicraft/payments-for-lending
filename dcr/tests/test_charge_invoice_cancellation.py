from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dcr.api import charge_invoice_cancellation as cancellation


class Doc(SimpleNamespace):
    def get(self, field, default=None):
        return getattr(self, field, default)

    def set_onload(self, field, value):
        self.onload[field] = value


@pytest.mark.parametrize('fields,scoped,expected', [
    ({}, True, True),
    ({'loan': None}, True, False),
    ({'is_return': 1}, True, False),
    ({'loan_disbursement': 'DISBURSEMENT'}, True, False),
    ({}, False, False),
])
def test_only_standalone_dcr_invoices_own_their_demand_cancellation(fields, scoped, expected):
    doc = Doc(name='INVOICE', loan='LOAN', onload={})
    doc.__dict__.update(fields)
    with patch.object(cancellation, 'floorplan_loan', return_value=scoped):
        cancellation.onload(doc)
    assert doc.onload == {'dcr_cancel_charge_demands_with_invoice': expected}


def test_all_remaining_charge_demands_cancel_inside_the_invoice_transaction():
    invoice = Doc(name='INVOICE', loan='LOAN', docstatus=2)
    rows = [
        Doc(name='NATIVE-FIRST', sales_invoice='INVOICE', loan='LOAN', demand_type='Charges', docstatus=2),
        Doc(name='SECOND', sales_invoice='INVOICE', loan='LOAN', demand_type='Charges', docstatus=1),
        Doc(name='THIRD', sales_invoice='INVOICE', loan='LOAN', demand_type='Charges', docstatus=1),
        Doc(name='OTHER', sales_invoice='OTHER', loan='LOAN', demand_type='Charges', docstatus=1),
        Doc(name='INTEREST', sales_invoice='INVOICE', loan='LOAN', demand_type='EMI', docstatus=1),
    ]
    events = []
    for row in rows:
        row.flags = Doc()

        def cancel(row=row):
            assert invoice.docstatus == 2, 'Parent must already be cancelled, so native makes no return'
            row.docstatus = 2
            events.append(row.name)
        row.cancel = cancel

    def get_all(doctype, filters, **kwargs):
        assert doctype == 'Loan Demand'
        return [r.name for r in rows if all(r.get(k) == v for k, v in filters.items())]

    with patch.object(cancellation, 'floorplan_loan', return_value=True), \
            patch.object(cancellation, 'frappe') as frappe:
        frappe.get_all.side_effect = get_all
        frappe.get_doc.side_effect = lambda doctype, name: next(r for r in rows if r.name == name)
        cancellation.on_cancel(invoice)
        cancellation.on_cancel(invoice)
    assert events == ['SECOND', 'THIRD']
    assert rows[3].docstatus == rows[4].docstatus == 1


def test_native_cancellation_failure_propagates_without_committing_a_partial_result():
    with patch.object(cancellation, 'floorplan_loan', return_value=True), \
            patch.object(cancellation, 'frappe') as frappe:
        frappe.get_all.return_value = ['PAID-DEMAND']
        frappe.get_doc.return_value.cancel.side_effect = ValueError('Cannot cancel paid demand')
        with pytest.raises(ValueError, match='Cannot cancel paid demand'):
            cancellation.on_cancel(Doc(name='INVOICE', loan='LOAN', docstatus=2))
        frappe.db.commit.assert_not_called()


@pytest.mark.parametrize('paid,waived,reject', [(0, 0, False), (25, 0, True), (0, 25, True)])
def test_paid_or_waived_charges_must_be_reversed_before_invoice_cancellation(paid, waived, reject):
    with patch.object(cancellation, 'floorplan_loan', return_value=True), \
            patch.object(cancellation, 'frappe') as frappe:
        frappe.get_all.return_value = [Doc(paid_amount=paid, waived_amount=waived)]
        frappe.throw.side_effect = ValueError('Cancel the associated charge payments and waivers')
        doc = Doc(name='INVOICE', loan='LOAN')
        if reject:
            with pytest.raises(ValueError, match='charge payments and waivers'):
                cancellation.before_cancel(doc)
        else:
            cancellation.before_cancel(doc)
            frappe.throw.assert_not_called()
