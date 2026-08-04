from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class PaymentResult:
    succeeded: bool
    reference: str
    failure_code: str | None = None


class PaymentGateway(Protocol):
    async def create_payment(self, *, order_id: str, amount: Decimal, currency: str) -> PaymentResult:
        ...
