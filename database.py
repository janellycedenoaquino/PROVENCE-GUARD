import sqlite3
from datetime import datetime, timezone

DB_PATH = "audit_log.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id   TEXT    NOT NULL,
                creator_id   TEXT    NOT NULL,
                timestamp    TEXT    NOT NULL,
                attribution  TEXT    NOT NULL,
                confidence   REAL    NOT NULL,
                llm_score    REAL    NOT NULL,
                style_score  REAL,
                status       TEXT    NOT NULL DEFAULT 'classified',
                appeal_reasoning  TEXT,
                appeal_timestamp  TEXT
            )
        """)
        conn.commit()


def log_submission(content_id, creator_id, attribution, confidence, llm_score, style_score):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO audit_log
                (content_id, creator_id, timestamp, attribution, confidence, llm_score, style_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'classified')
        """, (
            content_id,
            creator_id,
            datetime.now(timezone.utc).isoformat(),
            attribution,
            confidence,
            llm_score,
            style_score,
        ))
        conn.commit()


def log_appeal(content_id: str, reasoning: str) -> bool:
    """Updates the record to under_review and stores appeal details.
    Returns False if content_id not found."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT id FROM audit_log WHERE content_id = ?", (content_id,)
        )
        if cursor.fetchone() is None:
            return False
        conn.execute("""
            UPDATE audit_log
            SET status = 'under_review',
                appeal_reasoning = ?,
                appeal_timestamp = ?
            WHERE content_id = ?
        """, (reasoning, datetime.now(timezone.utc).isoformat(), content_id))
        conn.commit()
    return True


def get_log(limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT content_id, creator_id, timestamp, attribution,
                   confidence, llm_score, style_score, status,
                   appeal_reasoning, appeal_timestamp
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(row) for row in rows]
