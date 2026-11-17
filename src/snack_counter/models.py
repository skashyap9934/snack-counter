from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class OfficeId(str, Enum):
    OSLO = "oslo"
    BENGALURU = "bengaluru"


class Currency(str, Enum):
    NOK = "NOK"
    INR = "INR"
    EUR = "EUR"


class RefillStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    COMMITTED = "committed"
    PURCHASED = "purchased"
    CLAIM_SUBMITTED = "claim_submitted"
    REIMBURSED = "reimbursed"
    CANCELLED = "cancelled"


EMPTY_BOX_STATUSES = frozenset(
    {RefillStatus.OPEN, RefillStatus.ASSIGNED, RefillStatus.COMMITTED}
)
SPEND_STATUSES = frozenset(
    {
        RefillStatus.PURCHASED,
        RefillStatus.CLAIM_SUBMITTED,
        RefillStatus.REIMBURSED,
    }
)
# Committed holds a reservation once we know the amount; before purchase
# we do not yet have an amount, so only purchased+ later count as spend.


@dataclass(frozen=True)
class Office:
    id: OfficeId
    monthly_budget: Decimal
    currency: Currency
    channel: str


OFFICES = {
    OfficeId.OSLO: Office(
        OfficeId.OSLO, Decimal("6000"), Currency.NOK, "#snacks-oslo"
    ),
    OfficeId.BENGALURU: Office(
        OfficeId.BENGALURU, Decimal("15000"), Currency.INR, "#snacks-blr"
    ),
}


@dataclass(frozen=True)
class Visit:
    office: OfficeId
    start: date
    end: date

    def covers(self, office: OfficeId, on: date) -> bool:
        return self.office == office and self.start <= on <= self.end


@dataclass
class Volunteer:
    employee_id: str
    home_office: OfficeId
    payroll_currency: Currency
    in_office_days: set[date] = field(default_factory=set)
    leave_days: set[date] = field(default_factory=set)
    visits: list[Visit] = field(default_factory=list)

    def is_on_leave(self, on: date) -> bool:
        return on in self.leave_days

    def is_in_office(self, on: date) -> bool:
        return on in self.in_office_days

    def present_at(self, office: OfficeId, on: date) -> bool:
        if self.is_on_leave(on) or not self.is_in_office(on):
            return False
        if self.home_office == office:
            return True
        return any(v.covers(office, on) for v in self.visits)


@dataclass
class Refill:
    office: OfficeId
    id: UUID = field(default_factory=uuid4)
    status: RefillStatus = RefillStatus.OPEN
    reporter_id: str | None = None
    assigned_to: str | None = None
    assigned_at: datetime | None = None
    committed_at: datetime | None = None
    purchased_at: datetime | None = None
    amount: Decimal | None = None
    currency: Currency | None = None
    receipt_ref: str | None = None
    snack_note: str | None = None
    hr_claim_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    assignment_attempts: int = 0
    previous_assignees: list[str] = field(default_factory=list)

    def is_empty_box(self) -> bool:
        return self.status in EMPTY_BOX_STATUSES


class ClaimStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class HrClaim:
    id: str
    employee_id: str
    amount: Decimal
    currency: Currency
    description: str
    receipt_ref: str
    status: ClaimStatus = ClaimStatus.PENDING
    payroll_currency: Currency | None = None


@dataclass(frozen=True)
class Timeouts:
    commit_after_assign: timedelta = timedelta(hours=4)
    purchase_after_commit: timedelta = timedelta(hours=24)


@dataclass(frozen=True)
class MonthlyReportLine:
    office: OfficeId
    currency: Currency
    spent: Decimal
    budget: Decimal
    remaining: Decimal
    refill_count: int


@dataclass(frozen=True)
class MonthlyReport:
    year: int
    month: int
    lines: tuple[MonthlyReportLine, ...]
    total_eur: Decimal
    pending_reimbursement: tuple[MonthlyReportLine, ...]
    fx_to_eur: dict[Currency, Decimal]


class SnackCounterError(Exception):
    pass


class DuplicateActiveRefillError(SnackCounterError):
    pass


class NotAssigneeError(SnackCounterError):
    pass


class InvalidTransitionError(SnackCounterError):
    pass


class BudgetExceededError(SnackCounterError):
    pass


class NoEligibleVolunteerError(SnackCounterError):
    pass
