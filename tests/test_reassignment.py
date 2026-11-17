from snack_counter.models import OfficeId, RefillStatus
from tests.conftest import volunteer


def test_refill_nobody_completes_is_handed_to_someone_else(service, clock, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    first = refill.assigned_to
    assert first in {"ida", "lars"}

    clock.advance(hours=4)
    service.tick()

    refill = service.store.get_refill(refill.id)
    assert refill.status == RefillStatus.ASSIGNED
    assert refill.assigned_to is not None
    assert refill.assigned_to != first
    assert first in refill.previous_assignees


def test_original_assignee_cannot_commit_after_reassignment(service, clock, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    first = refill.assigned_to
    clock.advance(hours=4)
    service.tick()
    second = service.store.get_refill(refill.id).assigned_to

    import pytest
    from snack_counter.models import NotAssigneeError

    with pytest.raises(NotAssigneeError):
        service.commit(refill.id, first)
    service.commit(refill.id, second)
    assert service.store.get_refill(refill.id).status == RefillStatus.COMMITTED


def test_decline_reassigns_immediately(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    first = refill.assigned_to
    service.decline(refill.id, first)
    refill = service.store.get_refill(refill.id)
    assert refill.assigned_to != first
    assert refill.status == RefillStatus.ASSIGNED


def test_committed_but_no_receipt_is_released(service, clock, now):
    from datetime import timedelta

    today = now.date()
    tomorrow = today + timedelta(days=1)
    ida = volunteer("ida", OfficeId.OSLO, today)
    lars = volunteer("lars", OfficeId.OSLO, today)
    ida.in_office_days.add(tomorrow)
    lars.in_office_days.add(tomorrow)
    service.register_volunteer(ida)
    service.register_volunteer(lars)
    refill = service.report_empty(OfficeId.OSLO, "ida")
    first = refill.assigned_to
    service.commit(refill.id, first)
    clock.advance(hours=24)
    service.tick()
    refill = service.store.get_refill(refill.id)
    assert refill.status == RefillStatus.ASSIGNED
    assert refill.assigned_to != first


def test_no_eligible_volunteer_leaves_open_and_posts_channel(service, now, chat):
    refill = service.report_empty(OfficeId.OSLO, "ghost")
    assert refill.status == RefillStatus.OPEN
    assert refill.assigned_to is None
    assert any("nobody eligible" in m.body for m in chat.messages)
