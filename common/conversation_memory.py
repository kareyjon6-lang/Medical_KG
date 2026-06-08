from typing import Dict, List

from common.pg_memory_store import PgMemoryStore


def memory_prompt_block(store: PgMemoryStore, user_id: str) -> str:
    memories = store.get_memories(user_id)
    if not memories:
        return ""
    lines = [f"- {item['memory_key']}: {item['memory_value']}" for item in memories]
    return "长期记忆：\n" + "\n".join(lines)


def build_initial_history(store: PgMemoryStore, user_id: str, limit: int = 10) -> List[Dict[str, str]]:
    history = []
    memory_block = memory_prompt_block(store, user_id)
    if memory_block:
        history.append({"role": "system", "content": memory_block})
    history.extend(store.get_recent_messages(user_id, limit=limit))
    return history


def update_long_term_memory_from_turn(store: PgMemoryStore, user_id: str, user_message: str, assistant_message: str) -> None:
    watched_terms = []
    for term in ["禁忌", "组成", "剂量", "功效", "出处", "症状", "药材"]:
        if term in user_message:
            watched_terms.append(term)
    if watched_terms:
        store.upsert_memory(user_id, "preference", "用户近期关注：" + "、".join(watched_terms))
    if len(user_message) > 20:
        store.upsert_memory(user_id, "last_topic", user_message[:120])
