import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_DATABASE_URL = "sqlite:///data/app_memory.sqlite3"


class PgMemoryStore:
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
        ]
        with self._connect() as conn:
            for statement in statements:
                self._execute(conn, statement)
            self._ensure_chat_message_thread_id(conn)
            self._commit(conn)

    def create_user(self, username: str, password: str) -> Dict[str, Any]:
        clean_username = username.strip()
        if len(clean_username) < 2:
            raise ValueError("Username must be at least 2 characters.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")

        user = {
            "id": secrets.token_hex(16),
            "username": clean_username,
            "password_hash": hash_password(password),
        }
        with self._connect() as conn:
            self._execute(
                conn,
                "INSERT INTO users (id, username, password_hash) VALUES ({0}, {0}, {0})",
                [user["id"], user["username"], user["password_hash"]],
            )
            self._commit(conn)
        return {"id": user["id"], "username": user["username"]}

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            return None
        return {"id": user["id"], "username": user["username"]}

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT id, username, password_hash FROM users WHERE username = {0}",
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
                SELECT u.id, u.username, s.id AS session_id, s.token
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = {0} AND s.revoked_at IS NULL
                """,
                [token],
            )
        return rows[0] if rows else None

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

    def _query_raw(self, conn, statement: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        cursor = self._execute_raw(conn, statement, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _placeholder(self, statement: str) -> str:
        placeholder = "?" if self.is_sqlite else "%s"
        return statement.format(placeholder)

    def _commit(self, conn) -> None:
        conn.commit()


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
