import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class Database:
    """Persistent storage engine for audit sessions, findings, and metadata."""

    def __init__(self, db_url: str = "sqlite:///instance/documind.db"):
        self.db_url = db_url
        self.is_sqlite = db_url.startswith("sqlite:///")
        self._mem_conn = None

        if self.is_sqlite:
            # Extract path
            raw_path = db_url.replace("sqlite:///", "")
            if raw_path == ":memory:":
                self.db_path = ":memory:"
                self._mem_conn = sqlite3.connect(":memory:", timeout=20.0, check_same_thread=False)
                self._mem_conn.row_factory = sqlite3.Row
            else:
                self.db_path = Path(raw_path)
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.db_path = None

        self._init_schema()

    def _get_connection(self):
        if self._mem_conn is not None:
            return self._mem_conn

        if self.is_sqlite:
            conn = sqlite3.connect(str(self.db_path), timeout=20.0)
            conn.row_factory = sqlite3.Row
            return conn
        else:
            # PostgreSQL fallback via psycopg2 / psycopg if installed
            try:
                import psycopg2
                return psycopg2.connect(self.db_url)
            except Exception as e:
                logger.error(f"PostgreSQL connection failed ({e}). Falling back to local SQLite.")
                local_path = Path("instance/documind.db")
                local_path.parent.mkdir(parents=True, exist_ok=True)
                self.is_sqlite = True
                self.db_path = local_path
                conn = sqlite3.connect(str(self.db_path), timeout=20.0)
                conn.row_factory = sqlite3.Row
                return conn

    def _init_schema(self):
        """Initializes tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,
                    total_documents INTEGER DEFAULT 0,
                    total_pages INTEGER DEFAULT 0,
                    contradictions_count INTEGER DEFAULT 0,
                    consistent_count INTEGER DEFAULT 0,
                    missing_info_count INTEGER DEFAULT 0,
                    uncertain_count INTEGER DEFAULT 0,
                    summary_json TEXT NOT NULL,
                    findings_json TEXT NOT NULL,
                    documents_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_audit(
        self,
        session_id: str,
        summary: Dict[str, Any],
        findings: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        status: str = "completed"
    ) -> bool:
        """Persists audit session result."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO audit_sessions (
                    session_id, created_at, status,
                    total_documents, total_pages, contradictions_count,
                    consistent_count, missing_info_count, uncertain_count,
                    summary_json, findings_json, documents_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    status,
                    summary.get("total_documents", len(documents)),
                    summary.get("total_pages", 0),
                    summary.get("contradictions_count", 0),
                    summary.get("consistent_count", 0),
                    summary.get("missing_info_count", 0),
                    summary.get("uncertain_count", 0),
                    json.dumps(summary),
                    json.dumps(findings),
                    json.dumps(documents),
                )
            )
            conn.commit()
            return True

    def get_audit(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single audit session by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, created_at, status, total_documents, total_pages,
                       contradictions_count, consistent_count, missing_info_count,
                       uncertain_count, summary_json, findings_json, documents_json
                FROM audit_sessions
                WHERE session_id = ?
                """,
                (session_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            return {
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "status": row["status"],
                "total_documents": row["total_documents"],
                "total_pages": row["total_pages"],
                "contradictions_count": row["contradictions_count"],
                "consistent_count": row["consistent_count"],
                "missing_info_count": row["missing_info_count"],
                "uncertain_count": row["uncertain_count"],
                "summary": json.loads(row["summary_json"]),
                "findings": json.loads(row["findings_json"]),
                "documents": json.loads(row["documents_json"]),
            }

    def list_audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent audit sessions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, created_at, status, total_documents, total_pages,
                       contradictions_count, consistent_count, missing_info_count, uncertain_count
                FROM audit_sessions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "session_id": r["session_id"],
                    "created_at": r["created_at"],
                    "status": r["status"],
                    "total_documents": r["total_documents"],
                    "total_pages": r["total_pages"],
                    "contradictions_count": r["contradictions_count"],
                    "consistent_count": r["consistent_count"],
                    "missing_info_count": r["missing_info_count"],
                    "uncertain_count": r["uncertain_count"],
                }
                for r in rows
            ]

    def get_global_stats(self) -> Dict[str, Any]:
        """Calculates aggregated metrics across all stored audits."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_audits,
                    COALESCE(SUM(total_documents), 0) as total_docs_audited,
                    COALESCE(SUM(total_pages), 0) as total_pages_audited,
                    COALESCE(SUM(contradictions_count), 0) as total_contradictions,
                    COALESCE(SUM(consistent_count), 0) as total_consistent
                FROM audit_sessions
                """
            )
            row = cursor.fetchone()
            return {
                "total_audits": row["total_audits"] if row else 0,
                "total_docs_audited": row["total_docs_audited"] if row else 0,
                "total_pages_audited": row["total_pages_audited"] if row else 0,
                "total_contradictions": row["total_contradictions"] if row else 0,
                "total_consistent": row["total_consistent"] if row else 0,
            }
