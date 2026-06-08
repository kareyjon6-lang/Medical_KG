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
