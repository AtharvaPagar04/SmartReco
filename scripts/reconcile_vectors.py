import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import async_session_maker
from app.models import Course, VectorOutbox
from app.repositories.vector_outbox import create as create_outbox
from app.services.vector_store import VectorStore


async def reconcile(*, dry_run: bool = True, repair: bool = False, course_id: str | None = None, batch_size: int = 100) -> Counter:
    if repair:
        dry_run = False

    async with async_session_maker() as db:
        query = select(Course).order_by(Course.id)
        if course_id:
            UUID(course_id)
            query = query.where(Course.id == course_id)
        courses = list((await db.scalars(query)).all())

    store = VectorStore()
    try:
        try:
            points = await store.scroll_points(limit=batch_size)
        except Exception as exc:
            print(f"Qdrant unavailable: {str(exc)[:200]}", file=sys.stderr)
            return Counter({"unavailable": 1, "repairs_failed": 1})

        by_id = {str(point.id): point for point in points}
        counts = Counter()
        course_repairs: list[tuple[str, str]] = []

        for course in courses:
            point = by_id.pop(course.id, None)
            if not course.is_active:
                if point:
                    counts["unexpected_active_point"] += 1
                    course_repairs.append((course.id, "DELETE"))
                else:
                    counts["healthy"] += 1
                continue

            payload = getattr(point, "payload", None) or {} if point else None
            if not point:
                status = "missing"
            elif payload.get("version") != course.version:
                status = "stale_course_version"
            elif payload.get("embedding_model") != settings.mesh_embedding_model:
                status = "wrong_model"
            elif payload.get("embedding_dimension") != settings.vector_size:
                status = "wrong_dimension"
            elif payload.get("embedding_schema_version") != settings.embedding_schema_version:
                status = "wrong_schema_version"
            elif payload.get("course_id") != course.id or payload.get("is_active") is not True:
                status = "metadata_mismatch"
            else:
                status = "healthy"

            counts[status] += 1
            if status != "healthy":
                course_repairs.append((course.id, "UPSERT"))

        orphan_points = [] if course_id else list(by_id.values())
        counts["orphan_vector"] = len(orphan_points)

        repairs_attempted = 0
        repairs_queued = 0
        orphans_deleted = 0
        repairs_failed = 0
        failure_details: list[str] = []

        if repair:
            if course_repairs:
                async with async_session_maker() as db:
                    for item_id, operation in course_repairs:
                        repairs_attempted += 1
                        try:
                            course = await db.get(Course, item_id)
                            if not course and operation != "DELETE":
                                repairs_failed += 1
                                failure_details.append(f"Course {item_id} missing from database for repair")
                                continue

                            exists = await db.scalar(
                                select(VectorOutbox.id).where(
                                    VectorOutbox.course_id == item_id,
                                    VectorOutbox.operation == operation,
                                    VectorOutbox.course_version == (course.version if course else 1),
                                    VectorOutbox.status.in_(("PENDING", "PROCESSING")),
                                )
                            )
                            if exists:
                                continue

                            if course and operation == "UPSERT":
                                course.vector_status = "PENDING"

                            outbox_job = create_outbox(
                                course
                                or Course(
                                    id=item_id,
                                    title="Archived",
                                    slug="archived",
                                    category="Archived",
                                    short_description="",
                                    description="",
                                ),
                                operation,
                                datetime.now(timezone.utc).replace(tzinfo=None),
                            )
                            db.add(outbox_job)
                            repairs_queued += 1
                        except Exception as exc:
                            repairs_failed += 1
                            failure_details.append(f"Failed to queue repair for course {item_id}: {str(exc)[:200]}")
                    await db.commit()

            for point in orphan_points:
                point_id = str(point.id)
                repairs_attempted += 1
                try:
                    await store.delete(point_id)
                    verification_point = await store.get_point(point_id)
                    if verification_point is None:
                        orphans_deleted += 1
                    else:
                        repairs_failed += 1
                        failure_details.append(f"Orphan point {point_id} still exists in Qdrant after deletion attempt")
                except Exception as exc:
                    repairs_failed += 1
                    failure_details.append(f"Failed deleting orphan point {point_id}: {str(exc)[:200]}")

        counts["repairs_attempted"] = repairs_attempted
        counts["repairs_queued"] = repairs_queued
        counts["orphans_deleted"] = orphans_deleted
        counts["repairs_failed"] = repairs_failed

        output_lines = [
            f"Healthy: {counts['healthy']}",
            f"Orphan Vector: {counts['orphan_vector']}",
        ]

        for k in ("missing", "stale_course_version", "wrong_model", "wrong_dimension", "wrong_schema_version", "metadata_mismatch", "unexpected_active_point"):
            if counts[k] > 0:
                output_lines.append(f"{k.replace('_', ' ').title()}: {counts[k]}")

        if repair:
            output_lines.extend([
                f"Repairs Attempted: {repairs_attempted}",
                f"Orphans Deleted: {orphans_deleted}",
                f"Repairs Queued: {repairs_queued}",
                f"Repairs Failed: {repairs_failed}",
            ])

        print(" ".join(output_lines))

        if failure_details:
            print("\nRepair Failures:", file=sys.stderr)
            for detail in failure_details:
                print(f"  - {detail}", file=sys.stderr)

        return counts
    finally:
        store.close()


def cli() -> None:
    parser = argparse.ArgumentParser(description="SmartReco Vector Reconciliation Tool")
    parser.add_argument("--dry-run", action="store_true", help="Inspect state without modifying Qdrant or SQL outbox")
    parser.add_argument("--repair", action="store_true", help="Execute repairs (delete orphan points, queue course outbox jobs)")
    parser.add_argument("--course-id", help="Filter reconciliation to a single course ID")
    parser.add_argument("--batch-size", type=int, default=100, help="Number of points to scroll per batch")
    args = parser.parse_args()

    counts = asyncio.run(
        reconcile(
            dry_run=not args.repair,
            repair=args.repair,
            course_id=args.course_id,
            batch_size=max(1, min(args.batch_size, 500)),
        )
    )

    if counts.get("repairs_failed", 0) > 0 or counts.get("unavailable", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    cli()
