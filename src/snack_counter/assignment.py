from __future__ import annotations

from datetime import date

from snack_counter.models import OfficeId, Refill, RefillStatus, Volunteer


def completed_this_month(refills: list[Refill], employee_id: str, today: date) -> int:
    return sum(
        1
        for r in refills
        if r.assigned_to == employee_id
        and r.status
        in {
            RefillStatus.PURCHASED,
            RefillStatus.CLAIM_SUBMITTED,
            RefillStatus.REIMBURSED,
        }
        and r.purchased_at is not None
        and r.purchased_at.date().year == today.year
        and r.purchased_at.date().month == today.month
    )


def pick_buyer(
    office: OfficeId,
    volunteers: list[Volunteer],
    refills: list[Refill],
    today: date,
    exclude: set[str] | None = None,
) -> Volunteer | None:
    exclude = exclude or set()
    eligible = [
        v
        for v in volunteers
        if v.employee_id not in exclude and v.present_at(office, today)
    ]
    if not eligible:
        return None

    def sort_key(v: Volunteer) -> tuple[int, str]:
        return (completed_this_month(refills, v.employee_id, today), v.employee_id)

    return min(eligible, key=sort_key)
