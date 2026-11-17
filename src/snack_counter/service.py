from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from snack_counter.adapters import ChatClient, HrClient
from snack_counter.assignment import pick_buyer
from snack_counter.budget import build_monthly_report, remaining_budget, would_exceed
from snack_counter.clock import Clock
from snack_counter.models import (
    BudgetExceededError,
    ClaimStatus,
    InvalidTransitionError,
    MonthlyReport,
    NotAssigneeError,
    OFFICES,
    OfficeId,
    Refill,
    RefillStatus,
    Timeouts,
    Volunteer,
)
from snack_counter.store import InMemoryStore


class SnackCounterService:
    def __init__(
        self,
        store: InMemoryStore,
        chat: ChatClient,
        hr: HrClient,
        clock: Clock | None = None,
        timeouts: Timeouts | None = None,
    ) -> None:
        self.store = store
        self.chat = chat
        self.hr = hr
        self.clock = clock or Clock()
        self.timeouts = timeouts or Timeouts()

    def register_volunteer(self, volunteer: Volunteer) -> None:
        self.store.add_volunteer(volunteer)

    def report_empty(self, office: OfficeId, reporter_id: str) -> Refill:
        existing = self.store.active_empty_box(office)
        if existing:
            self.chat.dm(
                reporter_id,
                f"Already being handled ({existing.status.value}) "
                f"by {existing.assigned_to or 'unassigned'}.",
            )
            return existing

        now = self.clock.now()
        refill = Refill(
            office=office,
            reporter_id=reporter_id,
            created_at=now,
            currency=OFFICES[office].currency,
        )
        self.store.add_refill(refill)
        self.chat.post_channel(
            office,
            f"Snack box is empty. Tracking refill {refill.id.hex[:8]}.",
        )
        self._assign(refill.id)
        return self.store.get_refill(refill.id)

    def commit(self, refill_id: UUID, employee_id: str) -> Refill:
        now = self.clock.now()

        def apply(refill: Refill) -> None:
            if refill.status != RefillStatus.ASSIGNED:
                raise InvalidTransitionError(
                    f"Cannot commit from {refill.status.value}"
                )
            if refill.assigned_to != employee_id:
                raise NotAssigneeError(
                    f"{employee_id} is not assigned; {refill.assigned_to} is"
                )
            refill.status = RefillStatus.COMMITTED
            refill.committed_at = now

        refill = self.store.mutate(refill_id, apply)
        self.chat.post_channel(
            refill.office,
            f"{employee_id} is buying snacks (refill {refill.id.hex[:8]}).",
        )
        return refill

    def decline(self, refill_id: UUID, employee_id: str) -> Refill:
        def apply(refill: Refill) -> None:
            if refill.status != RefillStatus.ASSIGNED:
                raise InvalidTransitionError("Can only decline while assigned")
            if refill.assigned_to != employee_id:
                raise NotAssigneeError("Only the assignee can decline")
            refill.previous_assignees.append(employee_id)
            refill.assigned_to = None
            refill.assigned_at = None
            refill.status = RefillStatus.OPEN

        self.store.mutate(refill_id, apply)
        return self._assign(refill_id)

    def submit_purchase(
        self,
        refill_id: UUID,
        employee_id: str,
        amount: Decimal,
        receipt_ref: str,
        snack_note: str = "",
    ) -> Refill:
        now = self.clock.now()
        refill = self.store.get_refill(refill_id)
        office = OFFICES[refill.office]
        if amount <= 0:
            raise InvalidTransitionError("Amount must be positive")
        if would_exceed(
            self.store.list_refills(),
            refill.office,
            now.year,
            now.month,
            amount,
        ):
            remaining = remaining_budget(
                self.store.list_refills(), refill.office, now.year, now.month
            )
            raise BudgetExceededError(
                f"{amount} {office.currency.value} exceeds remaining "
                f"{remaining} {office.currency.value}"
            )

        def apply(r: Refill) -> None:
            if r.status != RefillStatus.COMMITTED:
                raise InvalidTransitionError(
                    f"Cannot purchase from {r.status.value}"
                )
            if r.assigned_to != employee_id:
                raise NotAssigneeError("Only the committed buyer can submit")
            r.amount = amount
            r.currency = office.currency
            r.receipt_ref = receipt_ref
            r.snack_note = snack_note
            r.purchased_at = now
            r.status = RefillStatus.PURCHASED

        refill = self.store.mutate(refill_id, apply)
        volunteer = self.store.get_volunteer(employee_id)
        claim_id = self.hr.create_claim(
            employee_id=employee_id,
            amount=amount,
            currency=office.currency,
            description=f"Snack refill {office.id.value}: {snack_note or 'snacks'}",
            receipt_ref=receipt_ref,
            payroll_currency=volunteer.payroll_currency,
        )

        def attach_claim(r: Refill) -> None:
            r.hr_claim_id = claim_id
            r.status = RefillStatus.CLAIM_SUBMITTED

        refill = self.store.mutate(refill_id, attach_claim)
        self.chat.dm(
            employee_id,
            f"Thanks. Claim {claim_id} filed for {amount} {office.currency.value}.",
        )
        self.chat.post_channel(
            refill.office,
            f"Box refilled by {employee_id} ({amount} {office.currency.value}).",
        )
        return refill

    def tick(self) -> None:
        """Reassign stale refills and poll HR. Call from a scheduler."""
        self._reassign_stale()
        self.poll_hr()

    def poll_hr(self) -> None:
        for refill in self.store.list_refills():
            if refill.status != RefillStatus.CLAIM_SUBMITTED or not refill.hr_claim_id:
                continue
            claim = self.hr.get_claim(refill.hr_claim_id)
            if claim.status == ClaimStatus.APPROVED:

                def mark(r: Refill, rid=refill.id) -> None:
                    r.status = RefillStatus.REIMBURSED

                self.store.mutate(refill.id, mark)
                if refill.assigned_to:
                    self.chat.dm(
                        refill.assigned_to,
                        f"Reimbursed for refill {refill.id.hex[:8]}.",
                    )
            elif claim.status == ClaimStatus.REJECTED:
                if refill.assigned_to:
                    self.chat.dm(
                        refill.assigned_to,
                        f"HR rejected claim {refill.hr_claim_id}. Please resubmit.",
                    )

    def monthly_report(self, year: int, month: int) -> MonthlyReport:
        return build_monthly_report(self.store.list_refills(), year, month)

    def _assign(self, refill_id: UUID) -> Refill:
        now = self.clock.now()
        refill = self.store.get_refill(refill_id)
        exclude = set(refill.previous_assignees)
        buyer = pick_buyer(
            refill.office,
            self.store.list_volunteers(),
            self.store.list_refills(),
            now.date(),
            exclude=exclude,
        )
        if buyer is None:
            self.chat.post_channel(
                refill.office,
                "Snack box is empty and nobody eligible is in the office today.",
            )
            return refill

        def apply(r: Refill) -> None:
            if r.status not in {RefillStatus.OPEN, RefillStatus.ASSIGNED}:
                return
            r.assigned_to = buyer.employee_id
            r.assigned_at = now
            r.status = RefillStatus.ASSIGNED
            r.assignment_attempts += 1

        refill = self.store.mutate(refill_id, apply)
        self.chat.dm(
            buyer.employee_id,
            f"You're up for snacks in {refill.office.value}. "
            f"Commit within {int(self.timeouts.commit_after_assign.total_seconds() // 3600)}h "
            f"with /snacks commit {refill.id.hex[:8]}",
        )
        self.chat.post_channel(
            refill.office,
            f"Assigned {buyer.employee_id} for refill {refill.id.hex[:8]}.",
        )
        return refill

    def _reassign_stale(self) -> None:
        now = self.clock.now()
        for refill in list(self.store.list_refills()):
            if refill.status == RefillStatus.ASSIGNED and refill.assigned_at:
                if now - refill.assigned_at >= self.timeouts.commit_after_assign:
                    self._release_and_reassign(refill.id, refill.assigned_to, "did not commit")
            elif refill.status == RefillStatus.COMMITTED and refill.committed_at:
                if now - refill.committed_at >= self.timeouts.purchase_after_commit:
                    self._release_and_reassign(
                        refill.id, refill.assigned_to, "did not submit a receipt"
                    )

    def _release_and_reassign(
        self, refill_id: UUID, previous: str | None, reason: str
    ) -> None:
        def apply(r: Refill) -> None:
            if previous:
                r.previous_assignees.append(previous)
            r.assigned_to = None
            r.assigned_at = None
            r.committed_at = None
            r.status = RefillStatus.OPEN

        self.store.mutate(refill_id, apply)
        if previous:
            self.chat.dm(previous, f"Refill reassigned because you {reason}.")
        self._assign(refill_id)
