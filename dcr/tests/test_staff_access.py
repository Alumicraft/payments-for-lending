"""Staff API authorization and permission-filtered chart aggregates."""
from unittest.mock import MagicMock, patch
import pytest
from dcr.api.access import require_staff, visible_chart_records
from dcr.api.dashboard import _chart_query


@pytest.mark.parametrize('user_type,user', [('Website User','dealer@example.test'), ('System User','Guest'), (None,'staff@example.test')])
def test_staff_guard_rejects_dealer_guest_and_unknown_user(user_type, user):
    with patch('dcr.api.access.frappe') as f:
        f.session.user = user; f.get_cached_value.return_value = user_type
        f.throw.side_effect = PermissionError
        with pytest.raises(PermissionError): require_staff('Loan', 'LOAN-OTHER')
        f.has_permission.assert_not_called()


def test_staff_guard_checks_requested_document_and_action():
    with patch('dcr.api.access.frappe') as f:
        f.session.user = 'staff@example.test'; f.get_cached_value.return_value = 'System User'
        require_staff('Bank Account', 'BANK-1', 'write')
        f.has_permission.assert_called_once_with('Bank Account', 'write', doc='BANK-1', throw=True)


def test_chart_visibility_uses_permission_filtered_get_list():
    with patch('dcr.api.access.frappe') as f:
        f.session.user = 'staff@example.test'; f.get_cached_value.return_value = 'System User'
        visible_chart_records('Home Build Request')
        f.get_list.assert_called_once_with('Home Build Request', pluck='name', limit_page_length=0)
        f.get_all.assert_not_called()


def test_empty_scope_never_issues_unrestricted_sql():
    with patch('dcr.api.dashboard.visible_chart_records', return_value=[]), patch('dcr.api.dashboard.frappe') as f:
        assert _chart_query('Loan', 'SELECT SUM(loan_amount) FROM `tabLoan` WHERE docstatus = 1', ()) == []
        f.db.sql.assert_not_called()


def test_scope_binds_names_without_interpolation():
    with patch('dcr.api.dashboard.visible_chart_records', return_value=['LOAN-1']), patch('dcr.api.dashboard.frappe') as f:
        _chart_query('Loan', 'SELECT SUM(loan_amount) FROM `tabLoan` WHERE docstatus = 1 AND creation >= %s', ('2026-01-01',))
        query, values = f.db.sql.call_args.args
        assert 'WHERE name IN %s AND docstatus' in query
        assert values == (('LOAN-1',), '2026-01-01')


def test_pipeline_scope_applies_to_outer_hbr_not_inner_receipt():
    with patch('dcr.api.dashboard.visible_chart_records', return_value=['HBR-1']), patch('dcr.api.dashboard.frappe') as f:
        _chart_query('Home Build Request', 'SELECT EXISTS(SELECT 1 WHERE po.docstatus = 1) FROM `tabHome Build Request` hbr WHERE docstatus = 1', ())
        query = f.db.sql.call_args.args[0]
        assert 'WHERE po.docstatus = 1' in query
        assert 'WHERE hbr.name IN %s AND docstatus' in query
