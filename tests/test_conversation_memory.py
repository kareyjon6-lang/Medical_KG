from common.conversation_memory import build_initial_history, memory_prompt_block
from common.pg_memory_store import PgMemoryStore


def test_build_initial_history_combines_recent_messages_and_memories(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'memory.db'}")
    store.init_schema()
    user = store.create_user("alice", "secret123")
    store.append_chat_message(user["id"], None, "user", "我想了解麻黄汤")
    store.append_chat_message(user["id"], None, "assistant", "可以关注组成和禁忌")
    store.upsert_memory(user["id"], "preference", "用户关注方剂禁忌")

    history = build_initial_history(store, user["id"], limit=4)

    assert history == [
        {"role": "system", "content": "长期记忆：\n- preference: 用户关注方剂禁忌"},
        {"role": "user", "content": "我想了解麻黄汤"},
        {"role": "assistant", "content": "可以关注组成和禁忌"},
    ]


def test_memory_prompt_block_returns_empty_string_without_memories(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'memory.db'}")
    store.init_schema()
    user = store.create_user("bob", "secret123")

    assert memory_prompt_block(store, user["id"]) == ""
