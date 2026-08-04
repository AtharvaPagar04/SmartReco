from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.csrf import validate_csrf_token
from app.database import get_db
from app.dependencies import get_user
from app.flash import flash
from app.models import ActivityEvent, Course, Order, OrderItem, User
from app.repositories.cart import get_cart_view
from app.routers.helpers import page
from app.services.cart_service import CartError, add_course_to_cart, remove_course_from_cart
from app.services.checkout_service import CheckoutError, complete_demo_payment, create_cart_order, create_single_course_order
from app.services.course_action_service import load_course_actions
from app.services.event_service import server_session_id

router = APIRouter()


async def _record_event(db: AsyncSession, request: Request, *, user_id: str, event_type: str, course_id: str | None = None, order_id: str | None = None) -> None:
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(ActivityEvent(user_id=user_id, session_id=server_session_id(request.session), event_type=event_type, course_id=course_id, metadata_json={"source": "commerce", "order_id": order_id} if order_id else {"source": "commerce"}, occurred_at=now, received_at=now))
        await db.commit()
    except Exception:
        await db.rollback()


@router.get("/cart")
async def cart_page(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    view = await get_cart_view(db, user_id=user.id)
    return page(request, "cart/index.html", current_user=user, cart=view)


@router.post("/cart/items/{course_slug}")
async def add_cart_item(course_slug: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    try:
        result = await add_course_to_cart(db, user_id=user.id, course_slug=course_slug)
        await db.commit()
        if result.added:
            course_id = await db.scalar(select(Course.id).where(Course.slug == course_slug))
            await _record_event(db, request, user_id=user.id, event_type="CART_ITEM_ADDED", course_id=course_id)
        flash(request, result.message, "success" if result.added else "info")
    except CartError as exc:
        await db.rollback()
        flash(request, str(exc), "warning")
    return RedirectResponse(f"/courses/{course_slug}", status_code=303)


@router.post("/cart/items/{course_slug}/remove")
async def remove_cart_item(course_slug: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    removed = await remove_course_from_cart(db, user_id=user.id, course_slug=course_slug)
    await db.commit()
    if removed:
        course_id = await db.scalar(select(Course.id).where(Course.slug == course_slug))
        await _record_event(db, request, user_id=user.id, event_type="CART_ITEM_REMOVED", course_id=course_id)
    flash(request, "Course removed from your cart." if removed else "Course was not in your cart.", "success" if removed else "info")
    return RedirectResponse("/cart", status_code=303)


@router.post("/courses/{slug}/buy")
async def buy_course(slug: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    try:
        order = await create_single_course_order(db, user_id=user.id, course_slug=slug)
    except CheckoutError as exc:
        await db.rollback()
        flash(request, str(exc), "warning")
        return RedirectResponse(f"/courses/{slug}", status_code=303)
    await _record_event(db, request, user_id=user.id, event_type="CHECKOUT_STARTED", order_id=order.id)
    return RedirectResponse(f"/checkout/{order.id}", status_code=303)


@router.post("/checkout")
async def checkout_cart(request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    try:
        order = await create_cart_order(db, user_id=user.id)
    except CheckoutError as exc:
        await db.rollback()
        flash(request, str(exc), "warning")
        return RedirectResponse("/cart", status_code=303)
    await _record_event(db, request, user_id=user.id, event_type="CHECKOUT_STARTED", order_id=order.id)
    return RedirectResponse(f"/checkout/{order.id}", status_code=303)


@router.get("/checkout/{order_id}")
async def checkout_page(order_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    order = await db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(404, "Order not found")
    return page(request, "cart/checkout.html", current_user=user, order=order)


@router.post("/checkout/{order_id}/complete")
async def complete_checkout(order_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    try:
        order = await complete_demo_payment(db, user_id=user.id, order_id=order_id)
    except CheckoutError as exc:
        await db.rollback()
        flash(request, str(exc), "warning")
        return RedirectResponse(f"/checkout/{order_id}", status_code=303)
    return RedirectResponse(f"/orders/{order.id}/success", status_code=303)


@router.post("/checkout/{order_id}/cancel")
async def cancel_checkout(order_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db), csrf_token: str = Form("")):
    validate_csrf_token(request, csrf_token)
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status == "PENDING":
        order.status = "CANCELLED"
        await db.commit()
        await _record_event(db, request, user_id=user.id, event_type="PURCHASE_CANCELLED", order_id=order.id)
    flash(request, "Checkout cancelled.", "info")
    return RedirectResponse("/cart", status_code=303)


@router.get("/orders/{order_id}/success")
async def purchase_success(order_id: str, request: Request, user: User = Depends(get_user), db: AsyncSession = Depends(get_db)):
    order = await db.scalar(select(Order).options(selectinload(Order.items).selectinload(OrderItem.course)).where(Order.id == order_id, Order.user_id == user.id, Order.status == "PAID"))
    if not order:
        raise HTTPException(404, "Purchase not found")
    actions = await load_course_actions(db, [item.course for item in order.items if item.course], user.id)
    return page(request, "cart/success.html", current_user=user, order=order, actions=actions)
