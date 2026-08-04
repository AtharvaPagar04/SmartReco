from decimal import Decimal

from app.models import Course
from app.services.course_action_service import action_for_course


def test_context_sensitive_actions(course):
    paid = Course(title="Paid", slug="paid", short_description="", description="", category="", tags=[], price=Decimal("10.00"), currency="USD", difficulty="BEGINNER", instructor="", duration_minutes=1)
    assert action_for_course(course, authenticated=False).primary_label == "Sign in to start"
    assert action_for_course(paid, authenticated=False).primary_label == "Sign in to buy"
    assert action_for_course(paid, authenticated=True).secondary_label == "Add to cart"
    in_cart = action_for_course(paid, authenticated=True, in_cart=True)
    assert (in_cart.primary_label, in_cart.secondary_label) == ("Buy course", "View cart")
    assert action_for_course(paid, authenticated=True, entitled=True).primary_label == "Start course"
