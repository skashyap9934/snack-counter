from __future__ import annotations

from threading import Lock
from uuid import UUID

from snack_counter.models import (
    EMPTY_BOX_STATUSES,
    OfficeId,
    Refill,
    Volunteer,
)


class InMemoryStore:
    """Thread-safe store so two commits cannot both succeed."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.volunteers: dict[str, Volunteer] = {}
        self.refills: dict[UUID, Refill] = {}

    def add_volunteer(self, volunteer: Volunteer) -> None:
        self.volunteers[volunteer.employee_id] = volunteer

    def get_volunteer(self, employee_id: str) -> Volunteer:
        return self.volunteers[employee_id]

    def list_volunteers(self) -> list[Volunteer]:
        return list(self.volunteers.values())

    def add_refill(self, refill: Refill) -> Refill:
        with self._lock:
            self.refills[refill.id] = refill
            return refill

    def get_refill(self, refill_id: UUID) -> Refill:
        return self.refills[refill_id]

    def list_refills(self) -> list[Refill]:
        return list(self.refills.values())

    def active_empty_box(self, office: OfficeId) -> Refill | None:
        for refill in self.refills.values():
            if refill.office == office and refill.status in EMPTY_BOX_STATUSES:
                return refill
        return None

    def mutate(self, refill_id: UUID, fn) -> Refill:
        """Apply fn(refill) under the lock. fn may raise to abort."""
        with self._lock:
            refill = self.refills[refill_id]
            fn(refill)
            return refill
