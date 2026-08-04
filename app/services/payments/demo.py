from decimal import Decimal

from app.services.payments.base import PaymentResult


class DemoPaymentGateway:
    async def create_payment(self, *, order_id: str, amount: Decimal, currency: str) -> PaymentResult:
        return PaymentResult(succeeded=True, reference=f"demo:{order_id}")
