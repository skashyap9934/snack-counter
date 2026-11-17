from datetime import datetime

import pytest

from snack_counter.adapters import FakeChat, FakeHr
from snack_counter.clock import FrozenClock
from snack_counter.models import OFFICES, Currency, OfficeId, Volunteer
from snack_counter.service import SnackCounterService
from snack_counter.store import InMemoryStore


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 11, 17, 9, 0, 0)


@pytest.fixture
def clock(now: datetime) -> FrozenClock:
    return FrozenClock(now)


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat({office.id: office.channel for office in OFFICES.values()})


@pytest.fixture
def hr() -> FakeHr:
    return FakeHr()


@pytest.fixture
def service(chat: FakeChat, hr: FakeHr, clock: FrozenClock) -> SnackCounterService:
    return SnackCounterService(InMemoryStore(), chat, hr, clock)


def volunteer(
    employee_id: str,
    office: OfficeId,
    on,
    *,
    currency: Currency | None = None,
) -> Volunteer:
    payroll = currency or (
        Currency.NOK if office == OfficeId.OSLO else Currency.INR
    )
    return Volunteer(
        employee_id=employee_id,
        home_office=office,
        payroll_currency=payroll,
        in_office_days={on},
    )
