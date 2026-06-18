import asyncio
from datetime import datetime, timedelta, timezone

from common.pg_memory_store import PgMemoryStore
from common.qa_cache import (
    SharedQaCacheService,
    normalize_question,
    question_hash,
    should_cache_answer,
)


def run_async(coro):
    return asyncio.run(coro)


def test_normalize_question_hashes_equivalent_punctuation():
    assert normalize_question("  你好？！ ") == normalize_question("你好")
    assert question_hash(normalize_question("你是谁？")) == question_hash(normalize_question("你是谁"))


def test_seed_daily_question_hits_shared_cache(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'qa.db'}")
    store.init_schema()
    service = SharedQaCacheService(store)
    service._redis_disabled = True

    cached = run_async(service.lookup("你好？"))

    assert cached["answer"] == "您好，请问您有什么中医相关的问题需要咨询？"
    assert cached["source"] == "pg_exact"
    entry = store.get_qa_cache_by_hash(question_hash(normalize_question("你好")))
    assert entry["answer_type"] == "daily"
    assert entry["is_seed"] is True


def test_generated_answer_can_be_reused_by_similar_question(monkeypatch, tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'qa.db'}")
    store.init_schema()
    service = SharedQaCacheService(store)
    service._redis_disabled = True

    answer = "麻黄汤具有发汗解表、宣肺平喘的作用，常用于外感风寒表实证相关表现。"
    saved = run_async(service.maybe_store_generated_answer("麻黄汤有什么功效？", answer))
    assert saved["quality_score"] >= 0.75

    async def always_confirm(_question, _entry):
        return True

    monkeypatch.setattr(service, "_verify_equivalent", always_confirm)
    cached = run_async(service.lookup("麻黄汤的功效是什么？"))

    assert cached["answer"] == answer
    assert cached["source"] in {"pg_similar", "pg_similar_verified"}


def test_postgres_exact_hit_backfills_redis(monkeypatch, tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'qa.db'}")
    store.init_schema()
    service = SharedQaCacheService(store)
    service._pg_seeded = True
    service._redis_seeded = True

    answer = "桂枝汤具有解肌发表、调和营卫的作用，常用于外感风寒表虚证相关表现。"
    run_async(service.maybe_store_generated_answer("桂枝汤有什么功效？", answer))
    backfilled = []

    async def redis_miss(_digest):
        return None

    async def capture_redis_set(entry, refresh_only=False):
        backfilled.append((entry, refresh_only))
        return True

    monkeypatch.setattr(service, "_redis_get", redis_miss)
    monkeypatch.setattr(service, "_redis_set", capture_redis_set)

    cached = run_async(service.lookup("桂枝汤有什么功效？"))

    assert cached["answer"] == answer
    assert cached["source"] == "pg_exact"
    assert backfilled
    assert backfilled[0][0]["answer"] == answer
    assert backfilled[0][1] is False


def test_seed_retries_redis_after_initial_unavailable(monkeypatch, tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'qa.db'}")
    store.init_schema()
    service = SharedQaCacheService(store)
    calls = []

    async def flaky_redis_set(entry, refresh_only=False):
        calls.append(entry["question"])
        return len(calls) > 20

    monkeypatch.setattr(service, "_redis_set", flaky_redis_set)

    run_async(service.ensure_seeded())
    assert service._pg_seeded is True
    assert service._redis_seeded is False

    service._last_redis_seed_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=31)
    run_async(service.ensure_seeded())
    assert service._redis_seeded is True
    assert len(calls) > 20


def test_answer_length_cache_limit_allows_up_to_2000_chars():
    assert should_cache_answer("mahuang tang effect", "a" * 1201)[0] is True
    assert should_cache_answer("guizhi tang effect", "a" * 2000)[0] is True
    assert should_cache_answer("xiaoqinglong tang effect", "a" * 2001)[0] is False


def test_bad_or_context_dependent_answers_are_not_cached():
    assert should_cache_answer("继续", "麻黄汤具有发汗解表、宣肺平喘的作用，常用于外感风寒表实证。")[0] is False
    assert should_cache_answer("肚子难受怎么办？", "回答生成中断，请稍后重试。")[0] is False
