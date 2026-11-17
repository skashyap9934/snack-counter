from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from snack_counter.models import ClaimStatus, Currency, HrClaim, OfficeId


@dataclass
class ChatMessage:
    target: str
    body: str


class ChatClient(Protocol):
    def dm(self, employee_id: str, body: str) -> None: ...

    def post_channel(self, office: OfficeId, body: str) -> None: ...


class HrClient(Protocol):
    def create_claim(
        self,
        employee_id: str,
        amount: Decimal,
        currency: Currency,
        description: str,
        receipt_ref: str,
        payroll_currency: Currency,
    ) -> str: ...

    def get_claim(self, claim_id: str) -> HrClaim: ...


class FakeChat(ChatClient):
    def __init__(self, channels: dict[OfficeId, str]) -> None:
        self.channels = channels
        self.messages: list[ChatMessage] = []

    def dm(self, employee_id: str, body: str) -> None:
        self.messages.append(ChatMessage(target=f"dm:{employee_id}", body=body))

    def post_channel(self, office: OfficeId, body: str) -> None:
        channel = self.channels[office]
        self.messages.append(ChatMessage(target=channel, body=body))

    def dms_to(self, employee_id: str) -> list[str]:
        key = f"dm:{employee_id}"
        return [m.body for m in self.messages if m.target == key]


class FakeHr(HrClient):
    def __init__(self) -> None:
        self.claims: dict[str, HrClaim] = {}

    def create_claim(
        self,
        employee_id: str,
        amount: Decimal,
        currency: Currency,
        description: str,
        receipt_ref: str,
        payroll_currency: Currency,
    ) -> str:
        claim_id = f"hr-{uuid4().hex[:8]}"
        self.claims[claim_id] = HrClaim(
            id=claim_id,
            employee_id=employee_id,
            amount=amount,
            currency=currency,
            description=description,
            receipt_ref=receipt_ref,
            payroll_currency=payroll_currency,
        )
        return claim_id

    def get_claim(self, claim_id: str) -> HrClaim:
        return self.claims[claim_id]

    def approve(self, claim_id: str) -> None:
        self.claims[claim_id].status = ClaimStatus.APPROVED

    def reject(self, claim_id: str) -> None:
        self.claims[claim_id].status = ClaimStatus.REJECTED
