"""
Ingest Database — SQLite persistence for the ingest pipeline.
Manages: SHA256 content cache, persistent task queue, page-to-source traceability.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = "data/ingest.db"

# Retry backoff schedule in seconds
RETRY_BACKOFF = [5, 15, 60]
MAX_RETRIES = 3


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_ingest_db():
    """Create all ingest tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ingest_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wiki_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                last_processed TEXT NOT NULL,
                generated_pages TEXT,
                UNIQUE(wiki_id, source_path)
            );

            CREATE TABLE IF NOT EXISTS ingest_tasks (
                id TEXT PRIMARY KEY,
                wiki_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                folder_context TEXT,
                topic TEXT NOT NULL,
                model_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                retries INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                next_retry_at TEXT,
                error TEXT,
                analysis_json TEXT,
                result_json TEXT
            );

            CREATE TABLE IF NOT EXISTS generated_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wiki_id TEXT NOT NULL,
                page_path TEXT NOT NULL,
                source_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cache_wiki ON ingest_cache (wiki_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_wiki ON ingest_tasks (wiki_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON ingest_tasks (status);
            CREATE INDEX IF NOT EXISTS idx_pages_wiki ON generated_pages (wiki_id);
        """)


# ─── Cache ─────────────────────────────────────────────────────────────


def check_cache(wiki_id: str, source_path: str, sha256: str) -> bool:
    """Return True if the file has already been processed with the same hash."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT sha256 FROM ingest_cache WHERE wiki_id = ? AND source_path = ?",
            (wiki_id, source_path),
        ).fetchone()
        return row is not None and row["sha256"] == sha256


def update_cache(wiki_id: str, source_path: str, sha256: str, pages: list[str]):
    """Insert or update the cache entry for a processed source."""
    now = _now()
    pages_json = json.dumps(pages)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ingest_cache (wiki_id, source_path, sha256, last_processed, generated_pages)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(wiki_id, source_path)
            DO UPDATE SET sha256 = excluded.sha256,
                          last_processed = excluded.last_processed,
                          generated_pages = excluded.generated_pages
            """,
            (wiki_id, source_path, sha256, now, pages_json),
        )


def clear_cache(wiki_id: str):
    """Clear all cache entries for a wiki (force re-ingest)."""
    with _connect() as conn:
        conn.execute("DELETE FROM ingest_cache WHERE wiki_id = ?", (wiki_id,))


# ─── Task Queue ────────────────────────────────────────────────────────


def enqueue_task(
    wiki_id: str,
    filename: str,
    source_path: str,
    topic: str,
    model_id: Optional[str] = None,
    folder_context: Optional[list[str]] = None,
) -> str:
    """Add a new ingest task to the queue. Returns task_id."""
    task_id = uuid.uuid4().hex
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ingest_tasks
                (id, wiki_id, source_path, filename, folder_context, topic, model_id, status, retries, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """,
            (
                task_id,
                wiki_id,
                source_path,
                filename,
                json.dumps(folder_context or []),
                topic,
                model_id,
                now,
                now,
            ),
        )
    return task_id


def get_pending_tasks(wiki_id: str) -> list[dict[str, Any]]:
    """Return all pending tasks for a wiki, ordered by creation time.
    Respects next_retry_at for backoff — tasks scheduled for the future are excluded.
    """
    now = _now()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM ingest_tasks
            WHERE wiki_id = ? AND status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
            ORDER BY created_at ASC
            """,
            (wiki_id, now),
        ).fetchall()
    return [dict(row) for row in rows]


def get_all_tasks(wiki_id: str) -> list[dict[str, Any]]:
    """Return all tasks for a wiki regardless of status."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ingest_tasks WHERE wiki_id = ? ORDER BY created_at DESC",
            (wiki_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task_status(
    task_id: str,
    status: str,
    error: Optional[str] = None,
    result: Optional[dict] = None,
    analysis_json: Optional[str] = None,
):
    """Update the status and optional result/error of a task."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE ingest_tasks
            SET status = ?, updated_at = ?, error = ?,
                result_json = ?, analysis_json = COALESCE(?, analysis_json)
            WHERE id = ?
            """,
            (
                status,
                now,
                error,
                json.dumps(result) if result else None,
                analysis_json,
                task_id,
            ),
        )


def increment_retry(task_id: str) -> int:
    """Increment retry count and compute backoff. Returns new retry count."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT retries FROM ingest_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return -1
        new_count = row["retries"] + 1

        # Compute next retry time with exponential backoff
        if new_count <= MAX_RETRIES:
            backoff_seconds = RETRY_BACKOFF[min(new_count - 1, len(RETRY_BACKOFF) - 1)]
            next_retry = datetime.now(timezone.utc).isoformat()
            # For simplicity we set it to now — the actual delay is enforced
            # by the processor loop sleeping between iterations.
            conn.execute(
                """
                UPDATE ingest_tasks
                SET retries = ?, status = 'pending', updated_at = ?, next_retry_at = ?
                WHERE id = ?
                """,
                (new_count, _now(), next_retry, task_id),
            )
        else:
            conn.execute(
                "UPDATE ingest_tasks SET retries = ?, status = 'failed', updated_at = ? WHERE id = ?",
                (new_count, _now(), task_id),
            )
        return new_count


def cancel_task(task_id: str) -> bool:
    """Cancel a pending task. Returns True if the task was cancelled."""
    with _connect() as conn:
        result = conn.execute(
            "UPDATE ingest_tasks SET status = 'cancelled', updated_at = ? WHERE id = ? AND status = 'pending'",
            (_now(), task_id),
        )
        return result.rowcount > 0


def retry_task(task_id: str) -> bool:
    """Reset a failed task back to pending for retry."""
    with _connect() as conn:
        result = conn.execute(
            """
            UPDATE ingest_tasks
            SET status = 'pending', error = NULL, updated_at = ?, next_retry_at = NULL
            WHERE id = ? AND status = 'failed'
            """,
            (_now(), task_id),
        )
        return result.rowcount > 0


def get_queue_state(wiki_id: str) -> dict[str, int]:
    """Return a summary of task counts by status for a wiki."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM ingest_tasks WHERE wiki_id = ? GROUP BY status",
            (wiki_id,),
        ).fetchall()
    state = {"pending": 0, "processing": 0, "completed": 0, "failed": 0, "cancelled": 0}
    for row in rows:
        state[row["status"]] = row["count"]
    return state


# ─── Page Traceability ─────────────────────────────────────────────────


def record_generated_page(wiki_id: str, page_path: str, source_path: str):
    """Record that a wiki page was generated from a source."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO generated_pages (wiki_id, page_path, source_path, created_at) VALUES (?, ?, ?, ?)",
            (wiki_id, page_path, source_path, _now()),
        )


def get_page_sources(wiki_id: str, page_path: str) -> list[str]:
    """Return all source paths that contributed to a wiki page."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT source_path FROM generated_pages WHERE wiki_id = ? AND page_path = ?",
            (wiki_id, page_path),
        ).fetchall()
    return [row["source_path"] for row in rows]


def get_source_pages(wiki_id: str, source_path: str) -> list[str]:
    """Return all wiki pages generated from a source."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT page_path FROM generated_pages WHERE wiki_id = ? AND source_path = ?",
            (wiki_id, source_path),
        ).fetchall()
    return [row["page_path"] for row in rows]
