from decimal import Decimal

import pytest

from snack_counter.models import (
    BudgetExceededError,
    Currency,
    NotAssigneeError,
    OfficeId,
    RefillStatus,
    Visit,
    Volunteer,
)
from tests.conftest import volunteer


def test_report_empty_assigns_someone_in_office(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    assert refill.status == RefillStatus.ASSIGNED
    assert refill.assigned_to == "ida"


def test_second_empty_report_does_not_create_another_refill(service, now, chat):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    first = service.report_empty(OfficeId.OSLO, "ida")
    second = service.report_empty(OfficeId.OSLO, "lars")
    assert first.id == second.id
    assert "Already being handled" in chat.dms_to("lars")[-1]


def test_non_assignee_cannot_commit(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    other = "lars" if refill.assigned_to == "ida" else "ida"
    with pytest.raises(NotAssigneeError):
        service.commit(refill.id, other)


def test_purchase_files_hr_claim(service, hr, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    service.commit(refill.id, "ida")
    refill = service.submit_purchase(
        refill.id, "ida", Decimal("500"), "img-1", "chocolate"
    )
    assert refill.status == RefillStatus.CLAIM_SUBMITTED
    claim = hr.get_claim(refill.hr_claim_id)
    assert claim.amount == Decimal("500")
    assert claim.currency == Currency.NOK
    assert claim.employee_id == "ida"


def test_hr_approval_marks_reimbursed(service, hr, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    service.commit(refill.id, "ida")
    refill = service.submit_purchase(refill.id, "ida", Decimal("500"), "img-1")
    hr.approve(refill.hr_claim_id)
    service.poll_hr()
    assert service.store.get_refill(refill.id).status == RefillStatus.REIMBURSED


def test_visitor_can_be_assigned_at_host_office(service, now):
    today = now.date()
    service.register_volunteer(
        Volunteer(
            "kari",
            OfficeId.OSLO,
            Currency.NOK,
            in_office_days={today},
            visits=[Visit(OfficeId.BENGALURU, today, today)],
        )
    )
    refill = service.report_empty(OfficeId.BENGALURU, "kari")
    assert refill.assigned_to == "kari"


def test_person_on_leave_is_not_assigned(service, now):
    today = now.date()
    service.register_volunteer(
        Volunteer(
            "ida",
            OfficeId.OSLO,
            Currency.NOK,
            in_office_days={today},
            leave_days={today},
        )
    )
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, today))
    refill = service.report_empty(OfficeId.OSLO, "lars")
    assert refill.assigned_to == "lars"


def test_hybrid_home_day_is_not_assigned(service, now):
    today = now.date()
    service.register_volunteer(
        Volunteer("ida", OfficeId.OSLO, Currency.NOK, in_office_days=set())
    )
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, today))
    refill = service.report_empty(OfficeId.OSLO, "anyone")
    assert refill.assigned_to == "lars"


def test_fairness_picks_person_with_fewer_refills_this_month(service, now, clock):
    today = now.date()
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, today))
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, today))
    r1 = service.report_empty(OfficeId.OSLO, "ida")
    first = r1.assigned_to
    service.commit(r1.id, first)
    service.submit_purchase(r1.id, first, Decimal("300"), "r1")

    r2 = service.report_empty(OfficeId.OSLO, "ida")
    assert r2.assigned_to != first
