"""Provider admission is durable; replay and uncertain sends cannot duplicate mail."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dcr.api import status_notices as api


@pytest.fixture
def delivery():
    notice = SimpleNamespace(status='Queued', email_queue=None, delivery_transport='Email Service',
        creation=datetime(2026,11,8,14,41), delivered_to='pilot@example.test',
        subject='HBR-1: Ordered', message='<p>Ordered</p>', save=MagicMock())
    settings = SimpleNamespace(enable_status_notifications=1,
        pilot_notifications_from='2026-11-08 14:40:00', pilot_notification_recipient='pilot@example.test')
    provider = MagicMock()
    provider.send_email.return_value = {'message_id': 'accepted-1'}
    branding = MagicMock()
    with patch.object(api,'frappe') as f, \
         patch.object(api,'get_datetime',side_effect=lambda value: value if isinstance(value,datetime) else datetime.fromisoformat(value)), \
         patch.dict('sys.modules',{'emails.email_service.vercel_client':provider,
                                  'emails.email_service.branding':branding}):
        f.get_doc.return_value = notice
        f.db.get_value.return_value = notice
        f.get_single.return_value = settings
        def update(doctype,name,values):
            for field,value in values.items():
                setattr(notice,field,value)
        f.db.set_value.side_effect = update
        yield f,notice,settings,provider


def test_service_acceptance_is_persisted_and_replay_does_not_send_again(delivery):
    f,notice,settings,provider = delivery
    def send(**kwargs):
        assert notice.status == 'Sending'
        assert f.db.commit.call_count == 1, 'The claim must survive a worker crash before the external call'
        assert kwargs['to_email'] == ['pilot@example.test']
        assert kwargs['data']['message'] == '<p>Ordered</p>'
        return {'message_id':'accepted-1'}
    provider.send_email.side_effect = send
    api._deliver_service_notice('NOTICE-1')
    assert notice.status == 'Sent'
    assert notice.provider_message_id == 'accepted-1'
    assert f.db.commit.call_count == 2
    assert f.db.get_value.call_args.kwargs['for_update'] is True
    api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_called_once()


@pytest.mark.parametrize('outcome',[TimeoutError('Unknown outcome'), {'message_id':None}])
def test_uncertain_provider_outcome_is_never_automatically_retried(delivery,outcome):
    f,notice,settings,provider = delivery
    if isinstance(outcome,Exception):
        provider.send_email.side_effect = outcome
    else:
        provider.send_email.return_value = outcome
    api._deliver_service_notice('NOTICE-1')
    assert notice.status == 'Outcome Unknown'
    assert notice.last_error
    assert f.db.commit.call_count == 2
    api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_called_once()


@pytest.mark.parametrize('change',[
    {'enable_status_notifications':0},
    {'pilot_notifications_from':None},
    {'pilot_notifications_from':'2026-11-08 14:42:00'},
    {'pilot_notification_recipient':'other@example.test'},
])
def test_disabled_or_changed_pilot_window_cannot_deliver_old_mail(delivery,change):
    f,notice,settings,provider = delivery
    for field,value in change.items():
        setattr(settings,field,value)
    api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_not_called()
    f.db.commit.assert_not_called()
    assert notice.status == 'Queued'


@pytest.mark.parametrize('status',['Sending','Sent','Outcome Unknown','Recorded','Error'])
def test_concurrent_worker_or_restarted_worker_never_reclaims_an_attempt(delivery,status):
    f,notice,settings,provider = delivery
    notice.status = status
    api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_not_called()
    f.db.commit.assert_not_called()


def test_configuration_failure_before_claim_can_be_corrected_without_sending(delivery):
    f,notice,settings,provider = delivery
    provider.get_service_config.side_effect = ValueError('Configuration missing')
    f.db.set_value.side_effect = None
    api._deliver_service_notice('NOTICE-1')
    assert notice.status == 'Queued'
    provider.send_email.assert_not_called()
    f.db.commit.assert_not_called()
    f.db.set_value.assert_called_once_with('DCR Status Notice','NOTICE-1','last_error','Configuration missing')


def test_failure_to_persist_claim_never_calls_provider(delivery):
    f,notice,settings,provider = delivery
    f.db.commit.side_effect = RuntimeError('Database unavailable')
    with pytest.raises(RuntimeError):
        api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_not_called()


def test_failure_to_persist_result_leaves_durable_claim_for_review(delivery):
    f,notice,settings,provider = delivery
    def update(doctype,name,values):
        if values.get('status') == 'Sending':
            notice.status = 'Sending'
        else:
            raise RuntimeError('Database unavailable')
    f.db.set_value.side_effect = update
    with pytest.raises(RuntimeError):
        api._deliver_service_notice('NOTICE-1')
    assert notice.status == 'Sending'
    api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_called_once()


def test_scheduler_dispatches_current_service_notices_in_a_bounded_batch(delivery):
    f,notice,settings,provider = delivery
    f.get_all.side_effect = [[],['FAILED','NEXT']]
    with patch.object(api,'_deliver_service_notice',side_effect=[RuntimeError('Claim failed'),None]) as deliver:
        api.refresh_notice_delivery()
    assert [call.args[0] for call in deliver.call_args_list] == ['FAILED','NEXT']
    f.db.rollback.assert_called_once()
    query = f.get_all.call_args.kwargs
    assert query['limit_page_length'] == 5
    assert query['order_by'] == 'creation asc'
    assert query['filters']['creation'] == ['>=','2026-11-08 14:40:00']
    assert query['filters']['delivered_to'] == 'pilot@example.test'


def test_current_locked_state_overrules_a_stale_document_snapshot(delivery):
    f,notice,settings,provider = delivery
    f.get_doc.return_value = SimpleNamespace(status='Queued')
    notice.status = 'Sending'
    api._deliver_service_notice('NOTICE-1')
    provider.send_email.assert_not_called()
    f.get_doc.assert_not_called()
