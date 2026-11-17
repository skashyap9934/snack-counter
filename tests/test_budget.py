from decimal import Decimal

import pytest

from snack_counter.budget import DEFAULT_FX_TO_EUR
from snack_counter.models import BudgetExceededError, Currency, OfficeId, RefillStatus
from tests.conftest import volunteer


def _buy(service, office, employee, amount, receipt):
    refill = service.report_empty(office, employee)
    service.commit(refill.id, employee)
    return service.submit_purchase(refill.id, employee, amount, receipt)


def test_oslo_budget_is_enforced_in_nok(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    _buy(service, OfficeId.OSLO, "ida", Decimal("5500"), "a")
    with pytest.raises(BudgetExceededError) as exc:
        _buy(service, OfficeId.OSLO, "ida", Decimal("600"), "b")
    assert "NOK" in str(exc.value)


def test_bengaluru_budget_is_independent_in_inr(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("arun", OfficeId.BENGALURU, now.date()))
    _buy(service, OfficeId.OSLO, "ida", Decimal("5500"), "osl")
    # Oslo is almost full; Bengaluru still has its own 15_000 INR.
    refill = _buy(service, OfficeId.BENGALURU, "arun", Decimal("3000"), "blr")
    assert refill.status == RefillStatus.CLAIM_SUBMITTED
    assert refill.currency == Currency.INR


def test_monthly_report_totals_both_currencies_and_eur(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("arun", OfficeId.BENGALURU, now.date()))
    _buy(service, OfficeId.OSLO, "ida", Decimal("1200"), "osl")
    _buy(service, OfficeId.BENGALURU, "arun", Decimal("2500"), "blr")

    report = service.monthly_report(2026, 11)
    by_office = {line.office: line for line in report.lines}

    assert by_office[OfficeId.OSLO].spent == Decimal("1200")
    assert by_office[OfficeId.OSLO].currency == Currency.NOK
    assert by_office[OfficeId.OSLO].remaining == Decimal("4800")
    assert by_office[OfficeId.BENGALURU].spent == Decimal("2500")
    assert by_office[OfficeId.BENGALURU].currency == Currency.INR
    assert by_office[OfficeId.BENGALURU].remaining == Decimal("12500")

    expected_eur = (
        Decimal("1200") * DEFAULT_FX_TO_EUR[Currency.NOK]
        + Decimal("2500") * DEFAULT_FX_TO_EUR[Currency.INR]
    ).quantize(Decimal("0.01"))
    assert report.total_eur == expected_eur


def test_spend_in_another_month_does_not_eat_this_months_budget(service, clock, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    _buy(service, OfficeId.OSLO, "ida", Decimal("5000"), "oct-end")

    clock.set(now.replace(month=12, day=1))
    service.register_volunteer(
        volunteer("ida", OfficeId.OSLO, clock.now().date())
    )
    refill = _buy(service, OfficeId.OSLO, "ida", Decimal("5000"), "dec")
    assert refill.amount == Decimal("5000")
    december = service.monthly_report(2026, 12)
    oslo = next(l for l in december.lines if l.office == OfficeId.OSLO)
    assert oslo.spent == Decimal("5000")
    november = service.monthly_report(2026, 11)
    oslo_nov = next(l for l in november.lines if l.office == OfficeId.OSLO)
    assert oslo_nov.spent == Decimal("5000")


def test_typical_purchase_bounds_fit_budgets():
    from snack_counter.models import OFFICES

    assert OFFICES[OfficeId.OSLO].monthly_budget == Decimal("6000")
    assert Decimal("300") <= Decimal("1200") <= OFFICES[OfficeId.OSLO].monthly_budget
    assert OFFICES[OfficeId.BENGALURU].monthly_budget == Decimal("15000")
    assert Decimal("500") <= Decimal("3000") <= OFFICES[OfficeId.BENGALURU].monthly_budget
