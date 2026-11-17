from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from snack_counter.models import (
    SPEND_STATUSES,
    Currency,
    MonthlyReport,
    MonthlyReportLine,
    OfficeId,
    OFFICES,
    Refill,
)


DEFAULT_FX_TO_EUR = {
    Currency.NOK: Decimal("0.085"),
    Currency.INR: Decimal("0.011"),
    Currency.EUR: Decimal("1"),
}


def in_month(when: datetime, year: int, month: int) -> bool:
    return when.year == year and when.month == month


def spent_in_month(
    refills: list[Refill], office: OfficeId, year: int, month: int
) -> Decimal:
    total = Decimal("0")
    for refill in refills:
        if refill.office != office:
            continue
        if refill.status not in SPEND_STATUSES or refill.amount is None:
            continue
        when = refill.purchased_at or refill.created_at
        if in_month(when, year, month):
            total += refill.amount
    return total


def remaining_budget(
    refills: list[Refill], office: OfficeId, year: int, month: int
) -> Decimal:
    office_cfg = OFFICES[office]
    return office_cfg.monthly_budget - spent_in_month(refills, office, year, month)


def would_exceed(
    refills: list[Refill],
    office: OfficeId,
    year: int,
    month: int,
    amount: Decimal,
) -> bool:
    return remaining_budget(refills, office, year, month) < amount


def build_monthly_report(
    refills: list[Refill],
    year: int,
    month: int,
    fx_to_eur: dict[Currency, Decimal] | None = None,
) -> MonthlyReport:
    fx = fx_to_eur or DEFAULT_FX_TO_EUR
    lines: list[MonthlyReportLine] = []
    total_eur = Decimal("0")
    for office_id, office in OFFICES.items():
        spent = spent_in_month(refills, office_id, year, month)
        count = sum(
            1
            for r in refills
            if r.office == office_id
            and r.status in SPEND_STATUSES
            and r.purchased_at
            and in_month(r.purchased_at, year, month)
        )
        lines.append(
            MonthlyReportLine(
                office=office_id,
                currency=office.currency,
                spent=spent,
                budget=office.monthly_budget,
                remaining=office.monthly_budget - spent,
                refill_count=count,
            )
        )
        total_eur += (spent * fx[office.currency]).quantize(Decimal("0.01"))

    pending_lines = []
    for office_id, office in OFFICES.items():
        pending = sum(
            (
                r.amount
                for r in refills
                if r.office == office_id
                and r.status.value == "claim_submitted"
                and r.amount is not None
            ),
            Decimal("0"),
        )
        if pending:
            pending_lines.append(
                MonthlyReportLine(
                    office=office_id,
                    currency=office.currency,
                    spent=pending,
                    budget=office.monthly_budget,
                    remaining=office.monthly_budget - pending,
                    refill_count=0,
                )
            )

    return MonthlyReport(
        year=year,
        month=month,
        lines=tuple(lines),
        total_eur=total_eur,
        pending_reimbursement=tuple(pending_lines),
        fx_to_eur=fx,
    )
