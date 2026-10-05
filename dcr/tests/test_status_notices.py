"""Persist transitions; atomically queue one controlled pilot notice."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from dcr.api.status_notices import record_transition, queue_pilot_notices, refresh_notice_delivery


@pytest.fixture
def f():
    with patch('dcr.api.status_notices.frappe') as f, patch('dcr.api.status_notices.get_url', return_value='https://pilot.example.test/portal'), patch('dcr.api.status_notices.queue_notification') as queue:
        f.sendmail = queue
        f.flags.in_migrate = False
        f.db.exists.return_value = None
        f.get_single.return_value = SimpleNamespace(enable_status_notifications=0,pilot_notification_recipient=None,staff_notification_recipient='staff@example.test')
        yield f


@pytest.fixture
def hbr():
    return SimpleNamespace(name='HBR-1',customer='DEALER-1',modified='2026-10-05 10:00:00')


def test_disabled_delivery_still_records_reviewable_notice(f,hbr):
    record_transition(hbr,'custom_order_stage','Pending','Ordered')
    data = f.get_doc.call_args.args[0]
    assert data['status'] == 'Recorded'
    assert data['event_key'] == data['name']
    f.sendmail.assert_not_called()


def test_duplicate_unchanged_or_migration_events_are_not_inserted(f,hbr):
    record_transition(hbr,'custom_order_stage','Ordered','Ordered')
    f.get_doc.assert_not_called()
    f.flags.in_migrate = True
    record_transition(hbr,'custom_order_stage','Pending','Ordered')
    f.get_doc.assert_not_called()
    f.flags.in_migrate = False; f.db.exists.return_value = 'EXISTS'
    record_transition(hbr,'custom_order_stage','Pending','Ordered')
    f.get_doc.assert_not_called()


def test_submission_notice_targets_staff_for_review(f,hbr):
    record_transition(hbr,'custom_portal_status','Draft','Submitted for Review')
    data = f.get_doc.call_args.args[0]
    assert data['audience'] == 'Staff'
    assert data['recipient'] == 'staff@example.test'


def test_storage_release_is_recorded(f,hbr):
    record_transition(hbr,'in_storage',1,0)
    assert 'Not In Storage' in f.get_doc.call_args.args[0]['subject']


def test_delivery_disabled_never_queues(f):
    queue_pilot_notices()
    f.get_all.assert_not_called()
    f.sendmail.assert_not_called()


def test_enabled_without_override_never_queues(f):
    f.get_single.return_value.enable_status_notifications = 1
    queue_pilot_notices()
    f.sendmail.assert_not_called()


def test_queue_routes_to_pilot_override_and_links_existing_queue(f):
    f.get_single.return_value.enable_status_notifications = 1
    f.get_single.return_value.pilot_notification_recipient = 'pilot@example.test'
    f.get_all.return_value = ['NOTICE-1']
    notice = f.get_doc.return_value
    notice.status = 'Recorded'; notice.recipient = 'real-dealer@example.test'
    f.sendmail.return_value.name = 'QUEUE-1'
    queue_pilot_notices()
    assert f.sendmail.call_args.kwargs['recipients'] == ['pilot@example.test']
    assert f.sendmail.call_args.kwargs['delayed'] is True
    assert notice.status == 'Queued'
    assert notice.email_queue == 'QUEUE-1'
    assert notice.delivered_to == 'pilot@example.test'


def test_already_queued_notice_is_not_requeued(f):
    f.get_single.return_value.enable_status_notifications = 1
    f.get_single.return_value.pilot_notification_recipient = 'pilot@example.test'
    f.get_all.return_value = ['NOTICE-1']; f.get_doc.return_value.status = 'Queued'
    queue_pilot_notices()
    f.sendmail.assert_not_called()


def test_queue_error_rolls_back_notice_and_queue_together(f):
    f.get_single.return_value.enable_status_notifications = 1
    f.get_single.return_value.pilot_notification_recipient = 'pilot@example.test'
    f.get_all.return_value = ['NOTICE-1']; f.get_doc.return_value.status = 'Recorded'
    f.sendmail.side_effect = ValueError('Missing outgoing account')
    queue_pilot_notices()
    f.db.rollback.assert_called_once_with(save_point='dcr_notice')
    f.get_doc.return_value.save.assert_not_called()


def test_sent_status_requires_actual_email_queue_readback(f):
    f.get_all.return_value = [SimpleNamespace(name='NOTICE-1',email_queue='QUEUE-1')]
    f.db.get_value.return_value = 'Sending'
    refresh_notice_delivery(); f.db.set_value.assert_not_called()
    f.db.get_value.return_value = 'Sent'
    refresh_notice_delivery(); f.db.set_value.assert_called_once_with('DCR Status Notice','NOTICE-1','status','Sent')


def test_native_queue_bypasses_immediate_shared_email_override():
    from dcr.api.notification_queue import queue_notification
    native=MagicMock(); patched=MagicMock()
    with patch.dict('sys.modules',{'frappe.email':SimpleNamespace(sendmail=native)}), patch('frappe.sendmail',patched):
        result=queue_notification(recipients=['pilot@example.test'],message='Notice',delayed=False,now=True)
        assert result is native.return_value
        assert native.call_args.kwargs['delayed'] is True
        assert native.call_args.kwargs['now'] is False
        patched.assert_not_called()
