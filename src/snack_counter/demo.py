"""Walkthrough script: bystander assignment, race, timeout, two currencies."""

from datetime import datetime
from decimal import Decimal

from snack_counter.adapters import FakeChat, FakeHr
from snack_counter.clock import FrozenClock
from snack_counter.models import OFFICES, Currency, OfficeId, Visit, Volunteer
from snack_counter.service import SnackCounterService
from snack_counter.store import InMemoryStore


def _service(now: datetime) -> tuple[SnackCounterService, FakeChat, FakeHr, FrozenClock]:
    clock = FrozenClock(now)
    chat = FakeChat({o.id: o.channel for o in OFFICES.values()})
    hr = FakeHr()
    svc = SnackCounterService(InMemoryStore(), chat, hr, clock)
    return svc, chat, hr, clock


def main() -> None:
    now = datetime(2026, 11, 17, 9, 0, 0)
    svc, chat, hr, clock = _service(now)

    oslo = [
        Volunteer("ida", OfficeId.OSLO, Currency.NOK, in_office_days={now.date()}),
        Volunteer("lars", OfficeId.OSLO, Currency.NOK, in_office_days={now.date()}),
        Volunteer("mei", OfficeId.OSLO, Currency.NOK, in_office_days={now.date()}),
    ]
    blr = [
        Volunteer("arun", OfficeId.BENGALURU, Currency.INR, in_office_days={now.date()}),
        Volunteer("priya", OfficeId.BENGALURU, Currency.INR, in_office_days={now.date()}),
    ]
    visitor = Volunteer(
        "kari",
        OfficeId.OSLO,
        Currency.NOK,
        in_office_days={now.date()},
        visits=[Visit(OfficeId.BENGALURU, now.date(), now.date())],
    )
    for v in oslo + blr + [visitor]:
        svc.register_volunteer(v)

    print("=== 1. Empty box -> assigned (no bystander wait) ===")
    r1 = svc.report_empty(OfficeId.OSLO, "anyone")
    print(f"  refill={r1.id.hex[:8]} status={r1.status.value} assignee={r1.assigned_to}")

    print("=== 2. Second reporter is told it is already covered ===")
    r1b = svc.report_empty(OfficeId.OSLO, "lars")
    print(f"  same id? {r1.id == r1b.id}  last DM to lars: {chat.dms_to('lars')[-1]}")

    print("=== 3. Timeout -> handed to someone else ===")
    first = r1.assigned_to
    clock.advance(hours=4)
    svc.tick()
    r1 = svc.store.get_refill(r1.id)
    print(f"  was {first}, now {r1.assigned_to} ({r1.status.value})")

    print("=== 4. Assignee commits and buys ===")
    buyer = r1.assigned_to
    assert buyer
    svc.commit(r1.id, buyer)
    svc.submit_purchase(r1.id, buyer, Decimal("450"), "receipt-osl-1", "Kvikk Lunsj, coffee")
    r1 = svc.store.get_refill(r1.id)
    print(f"  status={r1.status.value} claim={r1.hr_claim_id} amount={r1.amount} NOK")

    print("=== 5. Bengaluru spend in INR + visitor eligible ===")
    r2 = svc.report_empty(OfficeId.BENGALURU, "arun")
    print(f"  assigned {r2.assigned_to} (fairness / presence)")
    svc.commit(r2.id, r2.assigned_to)
    svc.submit_purchase(r2.id, r2.assigned_to, Decimal("1800"), "receipt-blr-1", "namkeen, soda")

    print("=== 6. HR approves Oslo; monthly report ===")
    hr.approve(r1.hr_claim_id)
    svc.poll_hr()
    report = svc.monthly_report(2026, 11)
    for line in report.lines:
        print(
            f"  {line.office.value}: {line.spent} {line.currency.value} "
            f"/ {line.budget} remaining {line.remaining}"
        )
    print(f"  combined (EUR, illustrative FX): {report.total_eur}")
    print("=== chat log ===")
    for m in chat.messages:
        print(f"  [{m.target}] {m.body}")


if __name__ == "__main__":
    main()
