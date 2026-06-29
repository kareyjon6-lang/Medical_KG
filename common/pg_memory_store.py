import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_DATABASE_URL = "sqlite:///data/app_memory.sqlite3"
_PLACEHOLDER_ENTITY_NAME_RE = re.compile(r"^[?？\uFFFD\s]+$")


def _is_placeholder_entity_name(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and bool(_PLACEHOLDER_ENTITY_NAME_RE.fullmatch(text))


def _extract_entity_name_from_summary(summary: Any) -> str:
    text = str(summary or "").strip()
    if not text:
        return ""
    if text.startswith("删除方药："):
        return text.split("：", 1)[1].strip()
    try:
        payload = json.loads(text)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    herb = payload.get("herb", {}) if isinstance(payload.get("herb"), dict) else {}
    deleted = payload.get("deleted", {}) if isinstance(payload.get("deleted"), dict) else {}
    return str(herb.get("name") or deleted.get("name") or "").strip()


def _resolve_knowledge_display_name(entity_name: Any, extracted_payload: Dict[str, Any], source_summary: Any = "") -> str:
    herb = extracted_payload.get("herb", {}) if isinstance(extracted_payload, dict) else {}
    deleted = extracted_payload.get("deleted", {}) if isinstance(extracted_payload, dict) else {}
    candidates = [
        entity_name,
        herb.get("name") if isinstance(herb, dict) else "",
        deleted.get("name") if isinstance(deleted, dict) else "",
        _extract_entity_name_from_summary(source_summary),
    ]
    for candidate in candidates:
        clean_name = str(candidate or "").strip()
        if clean_name and not _is_placeholder_entity_name(clean_name):
            return clean_name
    return ""


class PgMemoryStore:
    """统一管理用户、会话、对话历史与后台操作记录存储。"""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.is_sqlite = self.database_url.startswith("sqlite:")

    def init_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                revoked_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                focus_entity TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT,
                thread_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(session_id) REFERENCES user_sessions(id),
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT,
                thread_id TEXT NOT NULL,
                status TEXT NOT NULL,
                question TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                thoughts TEXT NOT NULL DEFAULT '',
                answer TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(session_id) REFERENCES user_sessions(id),
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_import_jobs (
                id TEXT PRIMARY KEY,
                admin_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                source_summary TEXT NOT NULL DEFAULT '',
                extracted_json TEXT NOT NULL DEFAULT '{}',
                operation_type TEXT NOT NULL DEFAULT 'legacy',
                entity_name TEXT NOT NULL DEFAULT '',
                is_committed INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                error TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                FOREIGN KEY(admin_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, memory_key),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS qa_cache_entries (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                normalized_question TEXT NOT NULL,
                question_hash TEXT NOT NULL UNIQUE,
                answer TEXT NOT NULL,
                question_tokens TEXT NOT NULL DEFAULT '[]',
                answer_type TEXT NOT NULL DEFAULT 'medical_qa',
                source TEXT NOT NULL DEFAULT 'generated',
                quality_score REAL NOT NULL DEFAULT 0,
                hit_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_hit_at TIMESTAMP,
                expires_at TIMESTAMP,
                is_seed INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_qa_cache_hash ON qa_cache_entries(question_hash)",
            "CREATE INDEX IF NOT EXISTS idx_qa_cache_active ON qa_cache_entries(is_active, expires_at, quality_score)",
        ]
        with self._connect() as conn:
            for statement in statements:
                self._execute(conn, statement)
            self._ensure_user_role(conn)
            self._ensure_chat_message_thread_id(conn)
            self._ensure_chat_jobs(conn)
            self._ensure_knowledge_import_jobs(conn)
            self._prune_legacy_knowledge_import_jobs(conn)
            self._commit(conn)
        self.ensure_default_admin()

    def create_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        clean_username = username.strip()
        if len(clean_username) < 2:
            raise ValueError("Username must be at least 2 characters.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        clean_role = "admin" if role == "admin" else "user"

        user = {
            "id": secrets.token_hex(16),
            "username": clean_username,
            "password_hash": hash_password(password),
            "role": clean_role,
        }
        with self._connect() as conn:
            self._execute(
                conn,
                "INSERT INTO users (id, username, password_hash, role) VALUES ({0}, {0}, {0}, {0})",
                [user["id"], user["username"], user["password_hash"], user["role"]],
            )
            self._commit(conn)
        return {"id": user["id"], "username": user["username"], "role": user["role"]}

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            return None
        return {"id": user["id"], "username": user["username"], "role": user.get("role") or "user"}

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT id, username, password_hash, role FROM users WHERE username = {0}",
                [username.strip()],
            )
        return rows[0] if rows else None

    def create_session(self, user_id: str) -> Dict[str, str]:
        session = {
            "id": secrets.token_hex(16),
            "user_id": user_id,
            "token": secrets.token_urlsafe(32),
        }
        with self._connect() as conn:
            self._execute(
                conn,
                "INSERT INTO user_sessions (id, user_id, token) VALUES ({0}, {0}, {0})",
                [session["id"], session["user_id"], session["token"]],
            )
            self._commit(conn)
        return session

    def revoke_session(self, token: str) -> None:
        with self._connect() as conn:
            self._execute(
                conn,
                "UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE token = {0}",
                [token],
            )
            self._commit(conn)

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT u.id, u.username, u.role, s.id AS session_id, s.token
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = {0} AND s.revoked_at IS NULL
                """,
                [token],
            )
        return rows[0] if rows else None

    def ensure_default_admin(self) -> None:
        username = os.getenv("TCM_ADMIN_USERNAME", "admin").strip()
        password = os.getenv("TCM_ADMIN_PASSWORD", "admin123")
        if not username or not password:
            return
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT id FROM users WHERE role = {0} LIMIT 1",
                ["admin"],
            )
            if rows:
                return
            existing = self._query(
                conn,
                "SELECT id FROM users WHERE username = {0} LIMIT 1",
                [username],
            )
            if existing:
                self._execute(
                    conn,
                    "UPDATE users SET role = {0} WHERE id = {0}",
                    ["admin", existing[0]["id"]],
                )
            else:
                self._execute(
                    conn,
                    "INSERT INTO users (id, username, password_hash, role) VALUES ({0}, {0}, {0}, {0})",
                    [secrets.token_hex(16), username, hash_password(password), "admin"],
                )
            self._commit(conn)

    def list_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT u.id,
                       u.username,
                       u.role,
                       u.created_at,
                       COUNT(DISTINCT m.id) AS message_count,
                       MAX(s.created_at) AS last_login_at
                FROM users u
                LEFT JOIN chat_messages m ON m.user_id = u.id
                LEFT JOIN user_sessions s ON s.user_id = u.id
                GROUP BY u.id, u.username, u.role, u.created_at
                ORDER BY u.created_at DESC, u.username ASC
                LIMIT {0}
                """,
                [int(limit)],
            )
        return [
            {
                "id": row["id"],
                "username": row["username"],
                "role": row.get("role") or "user",
                "created_at": str(row["created_at"]),
                "message_count": int(row["message_count"] or 0),
                "last_login_at": str(row["last_login_at"] or ""),
            }
            for row in rows
        ]

    def delete_user(self, user_id: str) -> bool:
        if not user_id:
            return False
        with self._connect() as conn:
            self._execute(conn, "DELETE FROM user_memories WHERE user_id = {0}", [user_id])
            self._execute(conn, "DELETE FROM chat_jobs WHERE user_id = {0}", [user_id])
            self._execute(conn, "DELETE FROM chat_messages WHERE user_id = {0}", [user_id])
            self._execute(conn, "DELETE FROM chat_threads WHERE user_id = {0}", [user_id])
            self._execute(conn, "DELETE FROM user_sessions WHERE user_id = {0}", [user_id])
            cursor = self._execute(conn, "DELETE FROM users WHERE id = {0}", [user_id])
            self._commit(conn)
        return bool(cursor.rowcount)

    def count_admins(self) -> int:
        with self._connect() as conn:
            rows = self._query(conn, "SELECT COUNT(*) AS count FROM users WHERE role = {0}", ["admin"])
        return int(rows[0]["count"] or 0) if rows else 0

    def create_chat_thread(self, user_id: str, title: str, focus_entity: Optional[str] = None) -> Dict[str, Any]:
        clean_title = (title or "").strip() or "新的对话"
        thread = {
            "id": secrets.token_hex(16),
            "user_id": user_id,
            "title": clean_title[:80],
            "focus_entity": (focus_entity or "").strip() or None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO chat_threads (id, user_id, title, focus_entity, created_at, updated_at)
                VALUES ({0}, {0}, {0}, {0}, {0}, {0})
                """,
                [
                    thread["id"],
                    thread["user_id"],
                    thread["title"],
                    thread["focus_entity"],
                    thread["created_at"],
                    thread["updated_at"],
                ],
            )
            self._commit(conn)
        return thread

    def get_chat_thread(self, user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
        if not thread_id:
            return None
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, user_id, title, focus_entity, created_at, updated_at
                FROM chat_threads
                WHERE user_id = {0} AND id = {0}
                """,
                [user_id, thread_id],
            )
        return rows[0] if rows else None

    def get_chat_threads(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT t.id,
                       t.title,
                       t.focus_entity,
                       t.created_at,
                       t.updated_at,
                       COUNT(m.id) AS message_count,
                       MAX(m.created_at) AS last_message_at
                FROM chat_threads t
                LEFT JOIN chat_messages m ON m.thread_id = t.id
                WHERE t.user_id = {0}
                GROUP BY t.id, t.title, t.focus_entity, t.created_at, t.updated_at
                ORDER BY COALESCE(MAX(m.created_at), t.updated_at) DESC, t.updated_at DESC
                LIMIT {0}
                """,
                [user_id, int(limit)],
            )
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "focus_entity": row["focus_entity"],
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "message_count": int(row["message_count"] or 0),
                "last_message_at": str(row["last_message_at"] or row["updated_at"]),
            }
            for row in rows
        ]

    def get_thread_messages(self, user_id: str, thread_id: str, limit: int = 100) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, session_id, thread_id, role, content, created_at
                FROM chat_messages
                WHERE user_id = {0} AND thread_id = {0}
                ORDER BY created_at ASC, id ASC
                LIMIT {0}
                """,
                [user_id, thread_id, int(limit)],
            )
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "thread_id": row["thread_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def clear_thread_messages(self, user_id: str, thread_id: str) -> int:
        if not thread_id:
            return 0
        with self._connect() as conn:
            cursor = self._execute(
                conn,
                """
                DELETE FROM chat_messages
                WHERE user_id = {0} AND thread_id = {0}
                """,
                [user_id, thread_id],
            )
            self._execute(
                conn,
                """
                UPDATE chat_threads
                SET updated_at = {0}
                WHERE user_id = {0} AND id = {0}
                """,
                [datetime.now(timezone.utc).isoformat(), user_id, thread_id],
            )
            self._commit(conn)
        return int(cursor.rowcount or 0)

    def delete_chat_thread(self, user_id: str, thread_id: str) -> bool:
        if not thread_id:
            return False
        with self._connect() as conn:
            self._execute(
                conn,
                """
                DELETE FROM chat_jobs
                WHERE user_id = {0} AND thread_id = {0}
                """,
                [user_id, thread_id],
            )
            self._execute(
                conn,
                """
                DELETE FROM chat_messages
                WHERE user_id = {0} AND thread_id = {0}
                """,
                [user_id, thread_id],
            )
            cursor = self._execute(
                conn,
                """
                DELETE FROM chat_threads
                WHERE user_id = {0} AND id = {0}
                """,
                [user_id, thread_id],
            )
            self._commit(conn)
        return bool(cursor.rowcount)

    def append_chat_message(
        self,
        user_id: str,
        session_id: Optional[str],
        role: str,
        content: str,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        message = {
            "id": secrets.token_hex(16),
            "user_id": user_id,
            "session_id": session_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO chat_messages (id, user_id, session_id, thread_id, role, content, created_at)
                VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0})
                """,
                [message["id"], user_id, session_id, thread_id, role, content, message["created_at"]],
            )
            if thread_id:
                self._execute(
                    conn,
                    "UPDATE chat_threads SET updated_at = {0} WHERE id = {0} AND user_id = {0}",
                    [message["created_at"], thread_id, user_id],
                )
            self._commit(conn)
        return message

    def create_chat_job(self, user_id: str, session_id: Optional[str], thread_id: str, question: str) -> Dict[str, Any]:
        job = {
            "id": secrets.token_hex(16),
            "user_id": user_id,
            "session_id": session_id,
            "thread_id": thread_id,
            "status": "queued",
            "question": question,
            "progress": 0,
            "thoughts": "",
            "answer": "",
            "error": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        }
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO chat_jobs (
                    id, user_id, session_id, thread_id, status, question, progress,
                    thoughts, answer, error, created_at, updated_at, finished_at
                )
                VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0})
                """,
                [
                    job["id"],
                    user_id,
                    session_id,
                    thread_id,
                    job["status"],
                    question,
                    job["progress"],
                    job["thoughts"],
                    job["answer"],
                    job["error"],
                    job["created_at"],
                    job["updated_at"],
                    job["finished_at"],
                ],
            )
            self._commit(conn)
        return job

    def update_chat_job(self, user_id: str, job_id: str, **fields) -> Optional[Dict[str, Any]]:
        allowed = {"status", "progress", "thoughts", "answer", "error", "finished_at"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_chat_job(user_id, job_id)
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{key} = {{0}}" for key in updates)
        values = list(updates.values()) + [user_id, job_id]
        with self._connect() as conn:
            self._execute(
                conn,
                f"UPDATE chat_jobs SET {assignments} WHERE user_id = {{0}} AND id = {{0}}",
                values,
            )
            self._commit(conn)
        return self.get_chat_job(user_id, job_id)

    def get_chat_job(self, user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        if not job_id:
            return None
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, user_id, session_id, thread_id, status, question, progress,
                       thoughts, answer, error, created_at, updated_at, finished_at
                FROM chat_jobs
                WHERE user_id = {0} AND id = {0}
                """,
                [user_id, job_id],
            )
        return self._public_job(rows[0]) if rows else None

    def get_active_chat_job(self, user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, user_id, session_id, thread_id, status, question, progress,
                       thoughts, answer, error, created_at, updated_at, finished_at
                FROM chat_jobs
                WHERE user_id = {0} AND thread_id = {0} AND status IN ({0}, {0})
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [user_id, thread_id, "queued", "running"],
            )
        return self._public_job(rows[0]) if rows else None

    def cancel_active_chat_jobs(self, user_id: str, thread_id: str, exclude_job_id: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            if exclude_job_id:
                cursor = self._execute(
                    conn,
                    """
                    UPDATE chat_jobs
                    SET status = {0}, updated_at = {0}, finished_at = {0}
                    WHERE user_id = {0} AND thread_id = {0} AND id <> {0} AND status IN ({0}, {0})
                    """,
                    ["cancelled", now, now, user_id, thread_id, exclude_job_id, "queued", "running"],
                )
            else:
                cursor = self._execute(
                    conn,
                    """
                    UPDATE chat_jobs
                    SET status = {0}, updated_at = {0}, finished_at = {0}
                    WHERE user_id = {0} AND thread_id = {0} AND status IN ({0}, {0})
                    """,
                    ["cancelled", now, now, user_id, thread_id, "queued", "running"],
                )
            self._commit(conn)
        return int(cursor.rowcount or 0)

    def create_knowledge_import_job(
        self,
        admin_id: str,
        source_type: str,
        file_name: str,
        source_summary: str,
        extracted_payload: Dict[str, Any],
        status: str = "extracted",
        error: str = "",
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "id": secrets.token_hex(16),
            "admin_id": admin_id,
            "source_type": source_type,
            "file_name": file_name or "",
            "source_summary": source_summary or "",
            "extracted_json": json.dumps(extracted_payload or {}, ensure_ascii=False),
            "status": status,
            "error": error or "",
            "created_at": now,
            "updated_at": now,
            "finished_at": now if status in {"imported", "failed"} else None,
        }
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO knowledge_import_jobs (
                    id, admin_id, source_type, file_name, source_summary, extracted_json,
                    status, error, created_at, updated_at, finished_at
                )
                VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0})
                """,
                [
                    job["id"],
                    admin_id,
                    job["source_type"],
                    job["file_name"],
                    job["source_summary"],
                    job["extracted_json"],
                    job["status"],
                    job["error"],
                    job["created_at"],
                    job["updated_at"],
                    job["finished_at"],
                ],
            )
            self._commit(conn)
        return self._public_knowledge_import_job(job)

    def create_knowledge_operation_record(
        self,
        admin_id: str,
        operation_type: str,
        entity_name: str,
        extracted_payload: Dict[str, Any],
        source_type: str = "manual",
        file_name: str = "",
        source_summary: str = "",
        error: str = "",
    ) -> Dict[str, Any]:
        clean_operation = operation_type if operation_type in {"add", "delete"} else "add"
        clean_entity_name = _resolve_knowledge_display_name(entity_name, extracted_payload, source_summary)
        if not clean_entity_name:
            raise ValueError("正式记录缺少有效的方药名称。")
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "id": secrets.token_hex(16),
            "admin_id": admin_id,
            "source_type": source_type or "manual",
            "file_name": file_name or "",
            "source_summary": source_summary or "",
            "extracted_json": json.dumps(extracted_payload or {}, ensure_ascii=False),
            "operation_type": clean_operation,
            "entity_name": clean_entity_name,
            "is_committed": 1,
            "status": "committed",
            "error": error or "",
            "created_at": now,
            "updated_at": now,
            "finished_at": now,
        }
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO knowledge_import_jobs (
                    id, admin_id, source_type, file_name, source_summary, extracted_json,
                    operation_type, entity_name, is_committed, status, error,
                    created_at, updated_at, finished_at
                )
                VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0})
                """,
                [
                    job["id"],
                    admin_id,
                    job["source_type"],
                    job["file_name"],
                    job["source_summary"],
                    job["extracted_json"],
                    job["operation_type"],
                    job["entity_name"],
                    job["is_committed"],
                    job["status"],
                    job["error"],
                    job["created_at"],
                    job["updated_at"],
                    job["finished_at"],
                ],
            )
            self._commit(conn)
        return self._public_knowledge_import_job(job)

    def update_knowledge_import_job(self, admin_id: str, job_id: str, **fields) -> Optional[Dict[str, Any]]:
        allowed = {"status", "error", "extracted_payload", "finished_at"}
        updates = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "extracted_payload":
                updates["extracted_json"] = json.dumps(value or {}, ensure_ascii=False)
            else:
                updates[key] = value
        if not updates:
            return self.get_knowledge_import_job(admin_id, job_id)
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{key} = {{0}}" for key in updates)
        values = list(updates.values()) + [admin_id, job_id]
        with self._connect() as conn:
            self._execute(
                conn,
                f"UPDATE knowledge_import_jobs SET {assignments} WHERE admin_id = {{0}} AND id = {{0}}",
                values,
            )
            self._commit(conn)
        return self.get_knowledge_import_job(admin_id, job_id)

    def get_knowledge_import_job(self, admin_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, admin_id, source_type, file_name, source_summary, extracted_json,
                       operation_type, entity_name, is_committed, status, error,
                       created_at, updated_at, finished_at
                FROM knowledge_import_jobs
                WHERE admin_id = {0} AND id = {0}
                """,
                [admin_id, job_id],
            )
        return self._public_knowledge_import_job(rows[0]) if rows else None

    def list_knowledge_import_jobs(self, admin_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, admin_id, source_type, file_name, source_summary, extracted_json,
                       operation_type, entity_name, is_committed, status, error,
                       created_at, updated_at, finished_at
                FROM knowledge_import_jobs
                WHERE admin_id = {0}
                  AND is_committed = 1
                  AND operation_type IN ({0}, {0})
                ORDER BY created_at DESC, id DESC
                LIMIT {0}
                """,
                [admin_id, "add", "delete", int(limit)],
            )
        return [self._public_knowledge_import_job(row) for row in rows]

    def get_recent_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = {0}
                ORDER BY created_at DESC, id DESC
                LIMIT {0}
                """,
                [user_id, int(limit)],
            )
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def get_chat_history(self, user_id: str, limit: int = 30) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT id, session_id, role, content, created_at
                FROM chat_messages
                WHERE user_id = {0}
                ORDER BY created_at DESC, id DESC
                LIMIT {0}
                """,
                [user_id, int(limit)],
            )
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": str(row["created_at"]),
            }
            for row in reversed(rows)
        ]

    def upsert_qa_cache_entry(
        self,
        question: str,
        normalized_question: str,
        question_hash: str,
        answer: str,
        question_tokens: List[str],
        answer_type: str = "medical_qa",
        source: str = "generated",
        quality_score: float = 0.0,
        expires_at: Optional[str] = None,
        is_seed: bool = False,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        tokens_json = json.dumps(question_tokens or [], ensure_ascii=False)
        with self._connect() as conn:
            existing = self._query(
                conn,
                "SELECT * FROM qa_cache_entries WHERE question_hash = {0} LIMIT 1",
                [question_hash],
            )
            if existing:
                current = self._public_qa_cache_entry(existing[0])
                current_quality = float(current.get("quality_score") or 0)
                should_replace_answer = quality_score >= current_quality
                params = [
                    question,
                    normalized_question,
                    tokens_json,
                    answer_type,
                    source,
                    float(max(quality_score, current_quality)),
                    expires_at,
                    1 if is_seed else int(current.get("is_seed") or 0),
                    1 if is_active else 0,
                    now,
                    question_hash,
                ]
                answer_assignment = "answer = {0}," if should_replace_answer else ""
                if should_replace_answer:
                    params.insert(3, answer)
                self._execute(
                    conn,
                    f"""
                    UPDATE qa_cache_entries
                    SET question = {{0}},
                        normalized_question = {{0}},
                        question_tokens = {{0}},
                        {answer_assignment}
                        answer_type = {{0}},
                        source = {{0}},
                        quality_score = {{0}},
                        expires_at = {{0}},
                        is_seed = {{0}},
                        is_active = {{0}},
                        updated_at = {{0}}
                    WHERE question_hash = {{0}}
                    """,
                    params,
                )
            else:
                self._execute(
                    conn,
                    """
                    INSERT INTO qa_cache_entries (
                        id, question, normalized_question, question_hash, answer,
                        question_tokens, answer_type, source, quality_score, hit_count,
                        created_at, updated_at, last_hit_at, expires_at, is_seed, is_active
                    )
                    VALUES ({0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0}, {0})
                    """,
                    [
                        secrets.token_hex(16),
                        question,
                        normalized_question,
                        question_hash,
                        answer,
                        tokens_json,
                        answer_type,
                        source,
                        float(quality_score),
                        0,
                        now,
                        now,
                        None,
                        expires_at,
                        1 if is_seed else 0,
                        1 if is_active else 0,
                    ],
                )
            self._commit(conn)
        entry = self.get_qa_cache_by_hash(question_hash, include_inactive=True)
        return entry or {}

    def get_qa_cache_by_hash(self, question_hash: str, include_inactive: bool = False) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        where = "question_hash = {0}"
        params: List[Any] = [question_hash]
        if not include_inactive:
            where += " AND is_active = {0} AND (expires_at IS NULL OR expires_at > {0})"
            params.extend([1, now])
        with self._connect() as conn:
            rows = self._query(
                conn,
                f"SELECT * FROM qa_cache_entries WHERE {where} LIMIT 1",
                params,
            )
        return self._public_qa_cache_entry(rows[0]) if rows else None

    def list_qa_cache_candidates(self, limit: int = 5000) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT *
                FROM qa_cache_entries
                WHERE is_active = {0}
                  AND quality_score >= {0}
                  AND (expires_at IS NULL OR expires_at > {0})
                ORDER BY hit_count DESC, quality_score DESC, updated_at DESC
                LIMIT {0}
                """,
                [1, 0.7, now, int(limit)],
            )
        return [self._public_qa_cache_entry(row) for row in rows]

    def record_qa_cache_hit(self, entry_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT hit_count, expires_at, is_seed FROM qa_cache_entries WHERE id = {0} LIMIT 1",
                [entry_id],
            )
            if not rows:
                return
            row = rows[0]
            next_hit_count = int(row.get("hit_count") or 0) + 1
            expires_at = row.get("expires_at")
            if not int(row.get("is_seed") or 0) and next_hit_count >= 10:
                hot_expires_at = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
                current_expires_at = str(expires_at or "")
                if not current_expires_at or current_expires_at < hot_expires_at:
                    expires_at = hot_expires_at
            self._execute(
                conn,
                """
                UPDATE qa_cache_entries
                SET hit_count = {0},
                    last_hit_at = {0},
                    updated_at = {0},
                    expires_at = {0}
                WHERE id = {0}
                """,
                [next_hit_count, now, now, expires_at, entry_id],
            )
            self._commit(conn)

    def prune_qa_cache_entries(self, max_entries: int = 50000) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE qa_cache_entries
                SET is_active = {0}, updated_at = {0}
                WHERE is_seed = {0}
                  AND expires_at IS NOT NULL
                  AND expires_at <= {0}
                """,
                [0, now, 0, now],
            )
            count_rows = self._query(conn, "SELECT COUNT(*) AS count FROM qa_cache_entries WHERE is_active = {0}", [1])
            active_count = int(count_rows[0]["count"] or 0) if count_rows else 0
            overflow = active_count - int(max_entries)
            if overflow > 0:
                self._execute(
                    conn,
                    """
                    UPDATE qa_cache_entries
                    SET is_active = {0}, updated_at = {0}
                    WHERE id IN (
                        SELECT id
                        FROM qa_cache_entries
                        WHERE is_seed = {0} AND is_active = {0}
                        ORDER BY quality_score ASC, hit_count ASC, COALESCE(last_hit_at, updated_at) ASC
                        LIMIT {0}
                    )
                    """,
                    [0, now, 0, 1, overflow],
                )
            self._commit(conn)

    def upsert_memory(self, user_id: str, memory_key: str, memory_value: str) -> None:
        if self.is_sqlite:
            statement = """
            INSERT INTO user_memories (id, user_id, memory_key, memory_value, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, memory_key)
            DO UPDATE SET memory_value = excluded.memory_value, updated_at = CURRENT_TIMESTAMP
            """
        else:
            statement = """
            INSERT INTO user_memories (id, user_id, memory_key, memory_value, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, memory_key)
            DO UPDATE SET memory_value = EXCLUDED.memory_value, updated_at = CURRENT_TIMESTAMP
            """
        with self._connect() as conn:
            self._execute_raw(conn, statement, [secrets.token_hex(16), user_id, memory_key, memory_value])
            self._commit(conn)

    def get_memories(self, user_id: str, limit: int = 20) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                """
                SELECT memory_key, memory_value
                FROM user_memories
                WHERE user_id = {0}
                ORDER BY updated_at DESC
                LIMIT {0}
                """,
                [user_id, int(limit)],
            )
        return [{"memory_key": row["memory_key"], "memory_value": row["memory_value"]} for row in rows]

    @contextmanager
    def _connect(self):
        if self.is_sqlite:
            path = self.database_url.replace("sqlite:///", "", 1)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
        else:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("PostgreSQL storage requires installing psycopg[binary].") from exc
            conn = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()

    def _execute(self, conn, statement: str, params: Iterable[Any] = ()):
        return self._execute_raw(conn, self._placeholder(statement), params)

    def _query(self, conn, statement: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        cursor = self._execute(conn, statement, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _execute_raw(self, conn, statement: str, params: Iterable[Any] = ()):
        cursor = conn.cursor()
        cursor.execute(statement, list(params))
        return cursor

    def _ensure_chat_message_thread_id(self, conn) -> None:
        if self.is_sqlite:
            columns = self._query_raw(conn, "PRAGMA table_info(chat_messages)")
            if not any(row.get("name") == "thread_id" for row in columns):
                self._execute_raw(conn, "ALTER TABLE chat_messages ADD COLUMN thread_id TEXT")
            return
        self._execute_raw(conn, "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS thread_id TEXT")

    def _ensure_chat_jobs(self, conn) -> None:
        if self.is_sqlite:
            return
        self._execute_raw(conn, "ALTER TABLE chat_jobs ADD COLUMN IF NOT EXISTS session_id TEXT")
        self._execute_raw(conn, "ALTER TABLE chat_jobs ADD COLUMN IF NOT EXISTS progress INTEGER NOT NULL DEFAULT 0")
        self._execute_raw(conn, "ALTER TABLE chat_jobs ADD COLUMN IF NOT EXISTS thoughts TEXT NOT NULL DEFAULT ''")
        self._execute_raw(conn, "ALTER TABLE chat_jobs ADD COLUMN IF NOT EXISTS answer TEXT NOT NULL DEFAULT ''")
        self._execute_raw(conn, "ALTER TABLE chat_jobs ADD COLUMN IF NOT EXISTS error TEXT NOT NULL DEFAULT ''")
        self._execute_raw(conn, "ALTER TABLE chat_jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP")

    def _ensure_knowledge_import_jobs(self, conn) -> None:
        if self.is_sqlite:
            columns = self._query_raw(conn, "PRAGMA table_info(knowledge_import_jobs)")
            names = {row.get("name") for row in columns}
            if "operation_type" not in names:
                self._execute_raw(conn, "ALTER TABLE knowledge_import_jobs ADD COLUMN operation_type TEXT NOT NULL DEFAULT 'legacy'")
            if "entity_name" not in names:
                self._execute_raw(conn, "ALTER TABLE knowledge_import_jobs ADD COLUMN entity_name TEXT NOT NULL DEFAULT ''")
            if "is_committed" not in names:
                self._execute_raw(conn, "ALTER TABLE knowledge_import_jobs ADD COLUMN is_committed INTEGER NOT NULL DEFAULT 0")
            return
        self._execute_raw(conn, "ALTER TABLE knowledge_import_jobs ADD COLUMN IF NOT EXISTS operation_type TEXT NOT NULL DEFAULT 'legacy'")
        self._execute_raw(conn, "ALTER TABLE knowledge_import_jobs ADD COLUMN IF NOT EXISTS entity_name TEXT NOT NULL DEFAULT ''")
        self._execute_raw(conn, "ALTER TABLE knowledge_import_jobs ADD COLUMN IF NOT EXISTS is_committed INTEGER NOT NULL DEFAULT 0")

    def _prune_legacy_knowledge_import_jobs(self, conn) -> None:
        self._execute(
            conn,
            """
            DELETE FROM knowledge_import_jobs
            WHERE is_committed <> {0}
               OR operation_type NOT IN ({0}, {0})
            """,
            [1, "add", "delete"],
        )

    def _ensure_user_role(self, conn) -> None:
        if self.is_sqlite:
            columns = self._query_raw(conn, "PRAGMA table_info(users)")
            if not any(row.get("name") == "role" for row in columns):
                self._execute_raw(conn, "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            return
        self._execute_raw(conn, "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user'")

    def _query_raw(self, conn, statement: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        cursor = self._execute_raw(conn, statement, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _placeholder(self, statement: str) -> str:
        placeholder = "?" if self.is_sqlite else "%s"
        return statement.replace("{0}", placeholder)

    def _commit(self, conn) -> None:
        conn.commit()

    def _public_qa_cache_entry(self, row: Dict[str, Any]) -> Dict[str, Any]:
        try:
            question_tokens = json.loads(row.get("question_tokens") or "[]")
        except Exception:
            question_tokens = []
        return {
            "id": row["id"],
            "question": row.get("question") or "",
            "normalized_question": row.get("normalized_question") or "",
            "question_hash": row.get("question_hash") or "",
            "answer": row.get("answer") or "",
            "question_tokens": question_tokens if isinstance(question_tokens, list) else [],
            "answer_type": row.get("answer_type") or "medical_qa",
            "source": row.get("source") or "generated",
            "quality_score": float(row.get("quality_score") or 0),
            "hit_count": int(row.get("hit_count") or 0),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "last_hit_at": str(row.get("last_hit_at") or ""),
            "expires_at": str(row.get("expires_at") or ""),
            "is_seed": bool(int(row.get("is_seed") or 0)),
            "is_active": bool(int(row.get("is_active") or 0)),
        }

    def _public_job(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "session_id": row.get("session_id"),
            "thread_id": row["thread_id"],
            "status": row["status"],
            "question": row["question"],
            "progress": int(row.get("progress") or 0),
            "thoughts": row.get("thoughts") or "",
            "answer": row.get("answer") or "",
            "error": row.get("error") or "",
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "finished_at": str(row.get("finished_at") or ""),
        }

    def _public_knowledge_import_job(self, row: Dict[str, Any]) -> Dict[str, Any]:
        try:
            extracted = json.loads(row.get("extracted_json") or "{}")
        except Exception:
            extracted = {}
        display_name = _resolve_knowledge_display_name(
            row.get("entity_name"),
            extracted if isinstance(extracted, dict) else {},
            row.get("source_summary"),
        )
        return {
            "id": row["id"],
            "admin_id": row["admin_id"],
            "source_type": row.get("source_type") or "",
            "file_name": row.get("file_name") or "",
            "source_summary": row.get("source_summary") or "",
            "extracted": extracted,
            "operation_type": row.get("operation_type") or "legacy",
            "entity_name": display_name,
            "display_name": display_name or "未知实体",
            "name_issue": "placeholder" if not display_name else "",
            "is_committed": bool(int(row.get("is_committed") or 0)),
            "status": row.get("status") or "draft",
            "error": row.get("error") or "",
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "finished_at": str(row.get("finished_at") or ""),
        }


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return hmac.compare_digest(digest.hex(), expected)


@contextmanager
def chat_turn(store: PgMemoryStore, user_id: str, session_id: Optional[str], user_message: str):
    store.append_chat_message(user_id, session_id, "user", user_message)
    result = {"assistant_message": ""}
    try:
        yield result
    finally:
        if result["assistant_message"]:
            store.append_chat_message(user_id, session_id, "assistant", result["assistant_message"])


def get_memory_store() -> PgMemoryStore:
    return PgMemoryStore()
