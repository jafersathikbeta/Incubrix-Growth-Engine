"""SQLite setup, schema creation, scoring helpers, and lead insertion logic."""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from src.config import get_settings

# Top English CPM markets for geo-targeting / scoring
TARGET_REGION_CODES = ("US", "GB", "CA", "AU", "IE", "NZ")
HIGH_CPM_COUNTRIES = set(TARGET_REGION_CODES) | {"UK"}
TOP_TIER_COUNTRIES = {"US", "GB", "UK"}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    channel_id TEXT PRIMARY KEY,
    channel_name TEXT NOT NULL,
    subscriber_count INTEGER DEFAULT 0,
    avg_views INTEGER DEFAULT 0,
    email TEXT DEFAULT '',
    linkedin TEXT DEFAULT '',
    instagram TEXT DEFAULT '',
    twitter TEXT DEFAULT '',
    country TEXT DEFAULT '',
    lead_score INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'B',
    has_monetization INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    pitch_draft TEXT DEFAULT '',
    email_status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS search_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    query TEXT,
    next_page_token TEXT,
    status TEXT,
    page_number INTEGER DEFAULT 1,
    min_subs INTEGER DEFAULT 0,
    max_subs INTEGER DEFAULT 10000000
);
"""


def get_db_path() -> Path:
    return get_settings().resolve_db_path()


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create leads and search_state tables; migrate older schemas."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)

        lead_cols = {row[1] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
        for col, ddl in (
            ("linkedin", "TEXT DEFAULT ''"),
            ("instagram", "TEXT DEFAULT ''"),
            ("twitter", "TEXT DEFAULT ''"),
            ("country", "TEXT DEFAULT ''"),
            ("lead_score", "INTEGER DEFAULT 0"),
            ("priority", "TEXT DEFAULT 'B'"),
            ("has_monetization", "INTEGER DEFAULT 0"),
        ):
            if col not in lead_cols:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {ddl}")

        state_cols = {row[1] for row in conn.execute("PRAGMA table_info(search_state)").fetchall()}
        if "page_number" not in state_cols:
            conn.execute(
                "ALTER TABLE search_state ADD COLUMN page_number INTEGER DEFAULT 1"
            )
        if "min_subs" not in state_cols:
            conn.execute(
                "ALTER TABLE search_state ADD COLUMN min_subs INTEGER DEFAULT 0"
            )
        if "max_subs" not in state_cols:
            conn.execute(
                "ALTER TABLE search_state ADD COLUMN max_subs INTEGER DEFAULT 10000000"
            )


def calculate_lead_score(
    subscriber_count: int,
    total_views: int = 0,
    avg_views: int = 0,
    country: str = "",
    has_monetization: int = 0,
) -> int:
    """
    Score a lead for B2B outreach qualification.
    Sweet spot: 10k–200k subscribers; US/UK countries score highest.
    Monetization signals (shop/course/sponsor/etc.) add a large boost.
    """
    subs = int(subscriber_count or 0)
    views = int(total_views or 0)
    if views <= 0 and avg_views:
        # Approximate reach when total views unavailable
        views = int(avg_views) * max(subs // 1000, 1)

    score = 0

    # Subscriber sweet spot (10k–200k)
    if 10_000 <= subs <= 200_000:
        score += 50
        if 40_000 <= subs <= 120_000:
            score += 15
    elif 5_000 <= subs < 10_000:
        score += 28
    elif 200_000 < subs <= 500_000:
        score += 22
    else:
        score += 8

    # Total views / reach
    if views >= 5_000_000:
        score += 30
    elif views >= 1_000_000:
        score += 22
    elif views >= 250_000:
        score += 14
    elif views >= 50_000:
        score += 8
    elif views > 0:
        score += 3

    cc = (country or "").strip().upper()
    if cc in TOP_TIER_COUNTRIES:
        score += 25
    elif cc in HIGH_CPM_COUNTRIES:
        score += 15
    elif cc:
        score += 5

    # Commercial intent — pushes monetized creators toward Priority A
    if int(has_monetization or 0) == 1:
        score += 50

    return int(score)


def assign_batch_priorities(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort by lead_score; top 5% of the batch become Priority A."""
    if not leads:
        return []
    ranked = sorted(leads, key=lambda x: int(x.get("lead_score") or 0), reverse=True)
    top_n = max(1, math.ceil(len(ranked) * 0.05))
    for i, lead in enumerate(ranked):
        lead["priority"] = "A" if i < top_n else "B"
    return ranked


def _has_any_contact(lead: Dict[str, Any]) -> bool:
    return bool(
        (lead.get("email") or "").strip()
        or (lead.get("linkedin") or "").strip()
        or (lead.get("instagram") or "").strip()
        or (lead.get("twitter") or "").strip()
    )


def insert_lead(lead: Dict[str, Any]) -> bool:
    """
    Insert a lead using INSERT OR IGNORE for 0% duplication.
    Requires channel_id, channel_name, and at least one contact method.
    """
    init_db()
    if not lead.get("channel_id") or not lead.get("channel_name"):
        raise ValueError("Lead missing required field: channel_id/channel_name")
    if not _has_any_contact(lead):
        raise ValueError("Lead missing contact method (email/linkedin/instagram/twitter)")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO leads (
                channel_id, channel_name, subscriber_count, avg_views,
                email, linkedin, instagram, twitter,
                country, lead_score, priority, has_monetization,
                description, pitch_draft, email_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead["channel_id"],
                lead["channel_name"],
                int(lead.get("subscriber_count") or 0),
                int(lead.get("avg_views") or 0),
                (lead.get("email") or "").strip(),
                (lead.get("linkedin") or "").strip(),
                (lead.get("instagram") or "").strip(),
                (lead.get("twitter") or "").strip(),
                (lead.get("country") or "").strip().upper(),
                int(lead.get("lead_score") or 0),
                (lead.get("priority") or "B").strip().upper() or "B",
                1 if int(lead.get("has_monetization") or 0) else 0,
                lead.get("description") or "",
                lead.get("pitch_draft") or "",
                lead.get("email_status") or "pending",
            ),
        )
        return cursor.rowcount > 0


def update_lead_score_priority(
    channel_id: str,
    lead_score: int,
    priority: str,
    country: str = "",
    has_monetization: int = 0,
) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE leads
            SET lead_score = ?,
                priority = ?,
                country = COALESCE(NULLIF(?, ''), country),
                has_monetization = ?
            WHERE channel_id = ?
            """,
            (
                int(lead_score),
                priority,
                (country or "").upper(),
                1 if int(has_monetization or 0) else 0,
                channel_id,
            ),
        )


def upsert_pitch(channel_id: str, pitch_draft: str) -> None:
    """Store a generated pitch draft for a lead."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET pitch_draft = ? WHERE channel_id = ?",
            (pitch_draft, channel_id),
        )


def update_email_status(channel_id: str, status: str) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET email_status = ? WHERE channel_id = ?",
            (status, channel_id),
        )


def get_all_leads() -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT channel_id, channel_name, subscriber_count, avg_views,
                   email, linkedin, instagram, twitter,
                   country, lead_score, priority, has_monetization,
                   description, pitch_draft, email_status
            FROM leads
            ORDER BY CASE WHEN priority = 'A' THEN 0 ELSE 1 END,
                     lead_score DESC,
                     subscriber_count DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_lead(channel_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    return dict(row) if row else None


def get_leads_with_drafts() -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM leads
            WHERE pitch_draft IS NOT NULL AND TRIM(pitch_draft) != ''
            ORDER BY CASE WHEN priority = 'A' THEN 0 ELSE 1 END,
                     lead_score DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def save_search_paused(
    query: str,
    next_page_token: Optional[str],
    page_number: int = 1,
    min_subs: int = 0,
    max_subs: int = 10_000_000,
) -> None:
    """Persist a paused scrape so the UI can resume tomorrow."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO search_state (id, query, next_page_token, status, page_number, min_subs, max_subs)
            VALUES (1, ?, ?, 'paused', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                query = excluded.query,
                next_page_token = excluded.next_page_token,
                status = 'paused',
                page_number = excluded.page_number,
                min_subs = excluded.min_subs,
                max_subs = excluded.max_subs
            """,
            (
                query,
                next_page_token or "",
                int(page_number),
                int(min_subs),
                int(max_subs),
            ),
        )


def mark_search_completed(query: str = "") -> None:
    """Mark the singleton search_state row as completed."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO search_state (id, query, next_page_token, status, page_number)
            VALUES (1, ?, '', 'completed', 1)
            ON CONFLICT(id) DO UPDATE SET
                query = COALESCE(NULLIF(excluded.query, ''), search_state.query),
                next_page_token = '',
                status = 'completed'
            """,
            (query,),
        )


def get_paused_search() -> Optional[Dict[str, Any]]:
    """Return the paused search_state row, or None."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, query, next_page_token, status, page_number, min_subs, max_subs
            FROM search_state
            WHERE id = 1 AND status = 'paused'
            """
        ).fetchone()
    return dict(row) if row else None


def get_search_state() -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM search_state WHERE id = 1"
        ).fetchone()
    return dict(row) if row else None


def primary_contact(lead: Dict[str, Any]) -> str:
    """Human-readable primary contact for CRM tables/cards."""
    if (lead.get("email") or "").strip():
        return f"Email: {lead['email'].strip()}"
    if (lead.get("linkedin") or "").strip():
        return f"LinkedIn: {lead['linkedin'].strip()}"
    if (lead.get("instagram") or "").strip():
        return f"Instagram: {lead['instagram'].strip()}"
    if (lead.get("twitter") or "").strip():
        return f"Twitter: {lead['twitter'].strip()}"
    return "No contact"
