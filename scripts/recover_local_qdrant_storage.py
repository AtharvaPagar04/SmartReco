"""
Development-Only Recovery Utility for Embedded Local Qdrant Storage.

UNSUPPORTED FOR PRODUCTION USE.
This tool performs low-level inspection and repair of local Qdrant SQLite storage
files when Python version transitions (e.g., Python 3.11 vs Python 3.14 pickle
protocol differences) prevent standard Qdrant Client API point deletion.
"""

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import pickle
import shutil
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import async_session_maker
from app.models import Course


def run_recovery(*, allow_recovery: bool, confirm: bool, target_point_ids: list[str] | None = None) -> int:
    """Perform direct inspection and recovery of local Qdrant SQLite storage.

    Returns exit code (0 for success, 1 for error/failure).
    """
    print("=" * 70)
    print("WARNING: LOCAL QDRANT STORAGE RECOVERY UTILITY")
    print("This is a local-development-only tool and is UNSUPPORTED for production.")
    print("=" * 70)

    if not allow_recovery:
        print("ERROR: Recovery aborted. Must pass --allow-local-storage-recovery.", file=sys.stderr)
        return 1

    if settings.qdrant_mode != "local":
        print(f"ERROR: Recovery refused. QDRANT_MODE is '{settings.qdrant_mode}'. Only 'local' mode is supported.", file=sys.stderr)
        return 1

    if not confirm:
        print("ERROR: Recovery aborted. Explicit confirmation flag --confirm is required.", file=sys.stderr)
        return 1

    sqlite_path = Path(settings.qdrant_path) / "collection" / settings.qdrant_collection / "storage.sqlite"
    if not sqlite_path.exists():
        print(f"ERROR: Qdrant local storage file not found at {sqlite_path}.", file=sys.stderr)
        return 1

    # Check lock file
    lock_file = Path(settings.qdrant_path) / ".lock"
    if lock_file.exists():
        try:
            with open(lock_file, "r+") as f:
                import portalocker
                portalocker.lock(f, portalocker.LockFlags.EXCLUSIVE | portalocker.LockFlags.NON_BLOCKING)
                portalocker.unlock(f)
        except Exception:
            print("ERROR: Embedded store is currently locked by another process (e.g. running uvicorn server).", file=sys.stderr)
            return 1

    # Create timestamped backup
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = sqlite_path.with_name(f"storage.sqlite.backup_{timestamp}")
    try:
        shutil.copy2(sqlite_path, backup_path)
        print(f"Backup created successfully: {backup_path}")
    except Exception as exc:
        print(f"ERROR: Failed to create backup before recovery: {exc}", file=sys.stderr)
        return 1

    # Verify SQL-backed courses to protect healthy vectors
    async def get_sql_course_ids():
        async with async_session_maker() as db:
            return set((await db.scalars(select(Course.id))).all())

    sql_course_ids = asyncio.run(get_sql_course_ids())
    print(f"Loaded {len(sql_course_ids)} active/stored SQL course IDs for protection.")

    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()

        # Verify internal table schema
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='points';")
        if not cursor.fetchone():
            print("ERROR: Expected internal table 'points' not found in storage.sqlite.", file=sys.stderr)
            conn.close()
            return 1

        cursor.execute("PRAGMA table_info(points);")
        columns = {col[1] for col in cursor.fetchall()}
        if "id" not in columns or "point" not in columns:
            print(f"ERROR: Expected columns ('id', 'point') missing from table 'points'. Found: {columns}", file=sys.stderr)
            conn.close()
            return 1

        cursor.execute("SELECT rowid, id FROM points;")
        rows = cursor.fetchall()
        deleted_count = 0
        failed_count = 0

        for rowid, raw_id in rows:
            try:
                point_id = pickle.loads(base64.b64decode(raw_id)) if isinstance(raw_id, str) else pickle.loads(raw_id)
                point_id_str = str(point_id)

                if point_id_str in sql_course_ids:
                    # Protected SQL course vector
                    continue

                if target_point_ids and point_id_str not in target_point_ids:
                    continue

                print(f"Targeting orphan point rowid {rowid}: ID '{point_id_str}'")
                cursor.execute("DELETE FROM points WHERE rowid = ?;", (rowid,))
                deleted_count += 1
            except Exception as exc:
                print(f"WARNING: Failed processing rowid {rowid}: {exc}", file=sys.stderr)
                failed_count += 1

        conn.commit()
        conn.close()

        print(f"Recovery summary: {deleted_count} orphan points deleted, {failed_count} failures.")
        return 0 if failed_count == 0 else 1
    except Exception as exc:
        print(f"ERROR: Storage recovery failed: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartReco Development-Only Qdrant Storage Recovery Utility")
    parser.add_argument("--allow-local-storage-recovery", action="store_true", help="Explicitly enable local storage recovery mode")
    parser.add_argument("--confirm", action="store_true", help="Confirm execution of low-level recovery")
    parser.add_argument("--point-ids", nargs="*", help="Optional list of specific point IDs to remove")
    args = parser.parse_args()

    code = run_recovery(
        allow_recovery=args.allow_local_storage_recovery,
        confirm=args.confirm,
        target_point_ids=args.point_ids,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
