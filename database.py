import sqlite3
import uuid
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
                style_score   REAL,
                word_len_score REAL,
                content_type  TEXT    NOT NULL DEFAULT 'text',
                status        TEXT    NOT NULL DEFAULT 'classified',
                appeal_reasoning  TEXT,
                appeal_timestamp  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verified_creators (
                creator_id            TEXT PRIMARY KEY,
                certificate_id        TEXT NOT NULL,
                verified_at           TEXT NOT NULL,
                verification_statement TEXT NOT NULL
            )
        """)
        conn.commit()


def is_eligible_for_certificate(creator_id: str) -> bool:
    """Creator is eligible if they have at least one likely_human classification."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
            SELECT id FROM audit_log
            WHERE creator_id = ? AND attribution = 'likely_human'
            LIMIT 1
        """, (creator_id,)).fetchone()
    return row is not None


def issue_certificate(creator_id: str, statement: str) -> dict:
    """Issues a certificate and returns its details."""
    certificate_id = f"cert-{str(uuid.uuid4())[:8]}"
    verified_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO verified_creators
                (creator_id, certificate_id, verified_at, verification_statement)
            VALUES (?, ?, ?, ?)
        """, (creator_id, certificate_id, verified_at, statement))
        conn.commit()
    return {"certificate_id": certificate_id, "verified_at": verified_at}


def get_certificate(creator_id: str) -> dict | None:
    """Returns certificate details for a creator, or None if not verified."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT certificate_id, verified_at
            FROM verified_creators WHERE creator_id = ?
        """, (creator_id,)).fetchone()
    return dict(row) if row else None


def log_submission(content_id, creator_id, attribution, confidence, llm_score, style_score, word_len_score, content_type="text"):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO audit_log
                (content_id, creator_id, timestamp, attribution, confidence,
                 llm_score, style_score, word_len_score, content_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'classified')
        """, (
            content_id,
            creator_id,
            datetime.now(timezone.utc).isoformat(),
            attribution,
            confidence,
            llm_score,
            style_score,
            word_len_score,
            content_type,
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


def get_analytics() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        total = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]

        breakdown_rows = conn.execute("""
            SELECT attribution, COUNT(*) AS n, ROUND(AVG(confidence), 4) AS avg_confidence
            FROM audit_log
            GROUP BY attribution
        """).fetchall()

        appeals = conn.execute("""
            SELECT COUNT(*) AS n FROM audit_log WHERE appeal_reasoning IS NOT NULL
        """).fetchone()["n"]

        verified = conn.execute(
            "SELECT COUNT(*) AS n FROM verified_creators"
        ).fetchone()["n"]

    attribution_breakdown = {}
    detection_rates = {}
    avg_confidence_by_attribution = {}

    for row in breakdown_rows:
        attr = row["attribution"]
        count = row["n"]
        attribution_breakdown[attr] = count
        detection_rates[f"{attr}_pct"] = round(count / total * 100, 1) if total else 0
        avg_confidence_by_attribution[attr] = row["avg_confidence"]

    return {
        "total_submissions": total,
        "attribution_breakdown": attribution_breakdown,
        "detection_rates": detection_rates,
        "appeal_rate": {
            "total_appeals": appeals,
            "rate_pct": round(appeals / total * 100, 1) if total else 0,
        },
        "avg_confidence_by_attribution": avg_confidence_by_attribution,
        "verified_creators": verified,
    }


def get_log(limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT content_id, creator_id, timestamp, attribution,
                   confidence, llm_score, style_score, word_len_score,
                   content_type, status, appeal_reasoning, appeal_timestamp
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(row) for row in rows]
