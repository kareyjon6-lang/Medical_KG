from datetime import datetime

from common.pg_memory_store import PgMemoryStore, get_memory_store


def test_user_registration_login_and_chat_history_roundtrip(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()

    user = store.create_user("alice", "secret123")
    assert user["username"] == "alice"
    assert store.verify_user("alice", "wrong") is None

    logged_in = store.verify_user("alice", "secret123")
    assert logged_in["id"] == user["id"]

    session = store.create_session(user["id"])
    assert store.get_user_by_token(session["token"])["username"] == "alice"

    store.append_chat_message(user["id"], session["id"], "user", "麻黄汤适合什么症状？")
    store.append_chat_message(user["id"], session["id"], "assistant", "麻黄汤常用于风寒表实证。")

    assert store.get_recent_messages(user["id"], limit=4) == [
        {"role": "user", "content": "麻黄汤适合什么症状？"},
        {"role": "assistant", "content": "麻黄汤常用于风寒表实证。"},
    ]


def test_long_term_memory_upserts_by_key(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    user = store.create_user("bob", "secret123")

    store.upsert_memory(user["id"], "preference", "用户关注方剂组成")
    store.upsert_memory(user["id"], "preference", "用户关注方剂禁忌")

    assert store.get_memories(user["id"]) == [
        {"memory_key": "preference", "memory_value": "用户关注方剂禁忌"}
    ]


def test_postgres_placeholder_conversion_preserves_json_default_literal():
    store = PgMemoryStore("postgresql://example")

    converted = store._placeholder(
        """
        CREATE TABLE IF NOT EXISTS knowledge_import_jobs (
            extracted_json TEXT NOT NULL DEFAULT '{}',
            admin_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            file_name TEXT NOT NULL DEFAULT ''
        )
        INSERT INTO users (id) VALUES ({0})
        """
    )

    assert "DEFAULT '{}'" in converted
    assert "VALUES (%s)" in converted


def test_chat_history_includes_message_metadata_in_chronological_order(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    user = store.create_user("charlie", "secret123")

    store.append_chat_message(user["id"], None, "user", "麻黄汤的组成是什么？")
    store.append_chat_message(user["id"], None, "assistant", "麻黄汤由麻黄、桂枝、杏仁、甘草组成。")

    history = store.get_chat_history(user["id"], limit=10)

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "麻黄汤的组成是什么？"
    assert history[0]["id"]
    assert history[0]["created_at"]


def test_get_memory_store_reads_database_url_at_call_time(monkeypatch, tmp_path):
    db_path = tmp_path / "call-time.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    store = get_memory_store()

    assert store.database_url == f"sqlite:///{db_path}"


def test_chat_threads_group_messages_and_update_focus(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    user = store.create_user("dana", "secret123")

    thread = store.create_chat_thread(user["id"], "麻黄汤禁忌", focus_entity="麻黄汤")
    store.append_chat_message(
        user["id"],
        None,
        "user",
        "麻黄汤有什么禁忌？",
        thread_id=thread["id"],
    )
    store.append_chat_message(
        user["id"],
        None,
        "assistant",
        "表虚自汗、阴虚盗汗者慎用。",
        thread_id=thread["id"],
    )

    threads = store.get_chat_threads(user["id"])
    assert threads[0]["id"] == thread["id"]
    assert threads[0]["title"] == "麻黄汤禁忌"
    assert threads[0]["focus_entity"] == "麻黄汤"
    assert threads[0]["message_count"] == 2

    messages = store.get_thread_messages(user["id"], thread["id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["thread_id"] == thread["id"]


def test_chat_jobs_track_status_and_cancel_active_jobs_by_thread(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    user = store.create_user("job_owner", "secret123")
    session = store.create_session(user["id"])
    first_thread = store.create_chat_thread(user["id"], "一号")
    second_thread = store.create_chat_thread(user["id"], "二号")

    first_job = store.create_chat_job(user["id"], session["id"], first_thread["id"], "第一个问题")
    second_job = store.create_chat_job(user["id"], session["id"], second_thread["id"], "第二个问题")
    store.update_chat_job(user["id"], first_job["id"], status="running", progress=34, thoughts="实体抽取完成")
    store.update_chat_job(user["id"], second_job["id"], status="running")

    assert store.get_active_chat_job(user["id"], first_thread["id"])["id"] == first_job["id"]
    assert store.cancel_active_chat_jobs(user["id"], first_thread["id"]) == 1
    assert store.get_chat_job(user["id"], first_job["id"])["status"] == "cancelled"
    assert store.get_chat_job(user["id"], second_job["id"])["status"] == "running"

    done = store.update_chat_job(
        user["id"],
        second_job["id"],
        status="done",
        progress=100,
        answer="第二个回答",
    )
    assert done["status"] == "done"
    assert done["answer"] == "第二个回答"
    assert done["progress"] == 100


def test_user_roles_listing_and_delete_cascade(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()

    admin = store.create_user("root_admin", "secret123", role="admin")
    user = store.create_user("managed_user", "secret123")
    session = store.create_session(user["id"])
    thread = store.create_chat_thread(user["id"], "测试对话", focus_entity="麻黄汤")
    store.append_chat_message(user["id"], session["id"], "user", "麻黄汤是什么？", thread_id=thread["id"])
    job = store.create_chat_job(user["id"], session["id"], thread["id"], "麻黄汤是什么？")
    store.upsert_memory(user["id"], "preference", "关注禁忌")

    users = store.list_users()
    assert any(item["id"] == admin["id"] and item["role"] == "admin" for item in users)
    assert any(item["id"] == user["id"] and item["message_count"] == 1 for item in users)
    assert store.count_admins() >= 1

    assert store.delete_user(user["id"]) is True
    assert store.get_user_by_username("managed_user") is None
    assert store.get_thread_messages(user["id"], thread["id"]) == []
    assert store.get_memories(user["id"]) == []
    assert store.get_chat_job(user["id"], job["id"]) is None


def test_knowledge_operation_records_roundtrip_and_prunes_legacy(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    admin = store.create_user("knowledge_admin", "secret123", role="admin")
    payload = {
        "herb": {"name": "阿胶鸡子黄汤", "label": "Formula", "effect": "养血滋阴"},
        "relations": [{"relation": "HAS_EFFECT", "object": "温经止血", "object_type": "Effect"}],
    }

    legacy = store.create_knowledge_import_job(
        admin["id"],
        "text",
        "",
        "错误旧记录。",
        payload,
    )
    assert legacy["is_committed"] is False
    assert store.list_knowledge_import_jobs(admin["id"]) == []

    added = store.create_knowledge_operation_record(
        admin["id"],
        "add",
        "阿胶鸡子黄汤",
        payload,
        source_summary="确认导入阿胶鸡子黄汤。",
    )
    deleted = store.create_knowledge_operation_record(
        admin["id"],
        "delete",
        "阿胶鸡子黄汤",
        {"deleted": {"name": "阿胶鸡子黄汤"}},
    )

    assert added["operation_type"] == "add"
    assert added["entity_name"] == "阿胶鸡子黄汤"
    assert added["is_committed"] is True
    assert deleted["operation_type"] == "delete"

    items = store.list_knowledge_import_jobs(admin["id"])
    assert [item["operation_type"] for item in items] == ["delete", "add"]
    assert all(item["is_committed"] for item in items)

    store.init_schema()
    assert [item["id"] for item in store.list_knowledge_import_jobs(admin["id"])] == [deleted["id"], added["id"]]


def test_qa_cache_hit_count_extends_hot_generated_entries(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    entry = store.upsert_qa_cache_entry(
        question="麻黄汤有什么功效？",
        normalized_question="麻黄汤有什么功效",
        question_hash="hot-cache-entry",
        answer="麻黄汤具有发汗解表、宣肺平喘的作用，常用于外感风寒表实证相关表现。",
        question_tokens=["麻黄汤", "功效"],
        answer_type="medical_qa",
        source="generated",
        quality_score=0.95,
        expires_at="2026-01-01T00:00:00+00:00",
        is_seed=False,
    )

    for _ in range(10):
        store.record_qa_cache_hit(entry["id"])

    updated = store.get_qa_cache_by_hash("hot-cache-entry")

    assert updated["hit_count"] == 10
    assert datetime.fromisoformat(updated["expires_at"]) > datetime.fromisoformat("2026-01-01T00:00:00+00:00")


def test_qa_cache_seed_hits_do_not_add_expiry(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'test.db'}")
    store.init_schema()
    entry = store.upsert_qa_cache_entry(
        question="你好",
        normalized_question="你好",
        question_hash="seed-cache-entry",
        answer="您好，请问您有什么中医相关的问题需要咨询？",
        question_tokens=["你好"],
        answer_type="daily",
        source="seed",
        quality_score=1.0,
        expires_at=None,
        is_seed=True,
    )

    for _ in range(10):
        store.record_qa_cache_hit(entry["id"])

    updated = store.get_qa_cache_by_hash("seed-cache-entry")

    assert updated["hit_count"] == 10
    assert updated["expires_at"] == ""
