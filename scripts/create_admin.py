import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import settings
from app.database import async_session_maker
from app.models import User
from app.security import hash_password, normalize_email


async def main():
    async with async_session_maker() as db:
        email = normalize_email(settings.admin_email)
        user = await db.scalar(select(User).where(User.email == email))
        if user:
            user.role = "ADMIN"
            user.is_active = True
            user.password_hash = hash_password(settings.admin_password)
            await db.commit()
            print(f"Updated existing admin account: {email}")
            return
        db.add(User(full_name="SmartReco Admin", email=email, password_hash=hash_password(settings.admin_password), role="ADMIN", is_active=True))
        await db.commit()
        print(f"Created admin account: {email}")


if __name__ == "__main__":
    asyncio.run(main())
