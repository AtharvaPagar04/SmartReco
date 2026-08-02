import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import async_session_maker
from app.models import Course, VectorOutbox
from app.services.vector_sync_service import process_one_job


async def main(args):
    async with async_session_maker() as db:
        query = select(Course).where(Course.is_active.is_(True)).order_by(Course.created_at).limit(args.batch_size if not args.force else 100000)
        if args.course_id:
            query = query.where(Course.id == args.course_id)
        courses = list((await db.execute(query)).scalars())
        if args.dry_run:
            print(f"Would rebuild {len(courses)} active course(s)")
            return
        jobs = []
        for course in courses:
            job = VectorOutbox(course_id=course.id, operation="UPSERT", course_version=course.version, payload=course.vector_payload(), next_attempt_at=datetime.now(timezone.utc).replace(tzinfo=None))
            db.add(job)
            jobs.append(job)
        await db.commit()
        ids = [job.id for job in jobs]
    for job_id in ids:
        await process_one_job(job_id)
    print(f"Queued and processed {len(ids)} course(s); inspect /admin/vector-sync for failures.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--course-id")
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args()))
