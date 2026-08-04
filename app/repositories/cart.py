from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CartItem, Course, ShoppingCart


@dataclass(frozen=True)
class CartView:
    cart: ShoppingCart
    items: list[CartItem]
    subtotal: Decimal


async def get_or_create_cart(db: AsyncSession, *, user_id: str) -> ShoppingCart:
    cart = await db.scalar(select(ShoppingCart).where(ShoppingCart.user_id == user_id))
    if cart:
        return cart
    cart = ShoppingCart(user_id=user_id)
    db.add(cart)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        cart = await db.scalar(select(ShoppingCart).where(ShoppingCart.user_id == user_id))
        if cart:
            return cart
        raise
    return cart


async def get_cart_view(db: AsyncSession, *, user_id: str) -> CartView:
    cart = await get_or_create_cart(db, user_id=user_id)
    items = list((await db.scalars(
        select(CartItem).options(selectinload(CartItem.course)).where(CartItem.cart_id == cart.id).order_by(CartItem.created_at, CartItem.id)
    )).all())
    subtotal = sum((Decimal(str(item.course.price)) for item in items if item.course and item.course.is_active), Decimal("0.00"))
    return CartView(cart=cart, items=items, subtotal=subtotal)


async def remove_cart_item(db: AsyncSession, *, user_id: str, course_id: str) -> bool:
    cart = await db.scalar(select(ShoppingCart).where(ShoppingCart.user_id == user_id))
    if not cart:
        return False
    result = await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id, CartItem.course_id == course_id))
    return bool(result.rowcount)
