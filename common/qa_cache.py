import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

REDIS_DAILY_TTL_SECONDS = 30 * 24 * 60 * 60
REDIS_MEDICAL_TTL_SECONDS = 14 * 24 * 60 * 60
PG_MEDICAL_TTL_DAYS = 90
PG_HOT_TTL_DAYS = 180
DIRECT_SIMILARITY_THRESHOLD = 0.88
VERIFY_SIMILARITY_THRESHOLD = 0.70
VERIFY_CONFIDENCE_THRESHOLD = 0.85
MAX_CANDIDATES = 5000


SEED_QA_PAIRS = [
    ("你好", "您好，请问您有什么中医相关的问题需要咨询？"),
    ("您好", "您好，请问您有什么中医相关的问题需要咨询？"),
    ("hello", "您好，请问您有什么中医相关的问题需要咨询？"),
    ("hi", "您好，请问您有什么中医相关的问题需要咨询？"),
    ("嗨", "您好，请问您有什么中医相关的问题需要咨询？"),
    ("在吗", "在的，请直接告诉我您想咨询的方剂、药材、功效、主治或症状问题。"),
    ("在嘛", "在的，请直接告诉我您想咨询的方剂、药材、功效、主治或症状问题。"),
    ("你是谁", "我是中医知识图谱问答助手，可以围绕方剂、药材、功效、主治、禁忌和关联图谱进行解释。"),
    ("你是什么", "我是中医知识图谱问答助手，可以围绕方剂、药材、功效、主治、禁忌和关联图谱进行解释。"),
    ("介绍一下你", "我是中医知识图谱问答助手，可以围绕方剂、药材、功效、主治、禁忌和关联图谱进行解释。"),
    ("你能做什么", "我可以结合中医知识图谱回答方剂、药材、功效、主治和禁忌相关问题。"),
    ("你会做什么", "我可以结合中医知识图谱回答方剂、药材、功效、主治和禁忌相关问题。"),
    ("谢谢", "不客气，您可以继续问我方剂、药材或症状相关问题。"),
    ("感谢", "不客气，您可以继续问我方剂、药材或症状相关问题。"),
    ("多谢", "不客气，您可以继续问我方剂、药材或症状相关问题。"),
    ("辛苦了", "不客气，您可以继续问我方剂、药材或症状相关问题。"),
    ("再见", "再见，祝您一切顺利。"),
    ("拜拜", "再见，祝您一切顺利。"),
    ("bye", "再见，祝您一切顺利。"),
    ("goodbye", "再见，祝您一切顺利。"),
]


def normalize_question(text: str) -> str:
    value = str(text or "").strip()
    punctuation_map = {
        "，": ",",
        "。": ".",
        "？": "?",
        "！": "!",
        "；": ";",
        "：": ":",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
    for source, target in punctuation_map.items():
        value = value.replace(source, target)
    value = re.sub(r"\s+", " ", value).strip().lower()
    value = value.strip(" ?!.。？！~～,，;；:")
    return value


def question_hash(normalized_question: str) -> str:
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


def tokenize_question(text: str) -> List[str]:
    normalized = normalize_question(text)
    if not normalized:
        return []
    try:
        import jieba

        tokens = [token.strip() for token in jieba.lcut(normalized) if token.strip()]
    except Exception:
        tokens = re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", normalized)
    if len(tokens) <= 1 and len(normalized) > 1:
        tokens.extend(normalized[index : index + 2] for index in range(len(normalized) - 1))
    return tokens


def _bm25_score(query_tokens: List[str], document_tokens: List[str], corpus_tokens: List[List[str]]) -> float:
    if not query_tokens or not document_tokens or not corpus_tokens:
        return 0.0
    doc_count = len(corpus_tokens)
    avg_doc_len = sum(len(tokens) for tokens in corpus_tokens) / max(1, doc_count)
    doc_len = len(document_tokens)
    k1 = 1.5
    b = 0.75
    score = 0.0
    doc_freqs = {}
    for token in set(query_tokens):
        doc_freqs[token] = sum(1 for tokens in corpus_tokens if token in tokens)
    for token in query_tokens:
        term_freq = document_tokens.count(token)
        if term_freq <= 0:
            continue
        doc_freq = doc_freqs.get(token, 0)
        idf = math.log(1 + (doc_count - doc_freq + 0.5) / (doc_freq + 0.5))
        denominator = term_freq + k1 * (1 - b + b * doc_len / max(avg_doc_len, 1))
        score += idf * (term_freq * (k1 + 1)) / max(denominator, 1e-6)
    return score


def _char_bigrams(text: str) -> List[str]:
    compact = re.sub(r"\s+", "", normalize_question(text))
    if len(compact) <= 1:
        return [compact] if compact else []
    return [compact[index : index + 2] for index in range(len(compact) - 1)]


def similarity_score(question: str, candidate: Dict[str, Any], corpus_tokens: List[List[str]]) -> float:
    query_normalized = normalize_question(question)
    candidate_normalized = candidate.get("normalized_question") or normalize_question(candidate.get("question", ""))
    query_tokens = tokenize_question(query_normalized)
    candidate_tokens = candidate.get("question_tokens") or tokenize_question(candidate_normalized)
    if not query_normalized or not candidate_normalized:
        return 0.0
    if query_normalized == candidate_normalized:
        return 1.0
    query_set = set(query_tokens)
    candidate_set = set(candidate_tokens)
    token_overlap = len(query_set & candidate_set)
    token_jaccard = token_overlap / max(1, len(query_set | candidate_set))
    token_containment = token_overlap / max(1, min(len(query_set), len(candidate_set)))
    query_bigrams = set(_char_bigrams(query_normalized))
    candidate_bigrams = set(_char_bigrams(candidate_normalized))
    bigram_overlap = len(query_bigrams & candidate_bigrams)
    bigram_jaccard = bigram_overlap / max(1, len(query_bigrams | candidate_bigrams))
    bigram_containment = bigram_overlap / max(1, min(len(query_bigrams), len(candidate_bigrams)))
    lexical_overlap = max(token_jaccard, token_containment, bigram_jaccard, bigram_containment)
    sequence_ratio = SequenceMatcher(None, query_normalized, candidate_normalized).ratio()
    bm25_raw = _bm25_score(query_tokens, candidate_tokens, corpus_tokens)
    bm25_normalized = bm25_raw / (bm25_raw + 4.0) if bm25_raw > 0 else 0.0
    score = min(1.0, 0.40 * sequence_ratio + 0.45 * lexical_overlap + 0.15 * bm25_normalized)
    if lexical_overlap >= 0.70 and sequence_ratio >= 0.55:
        score = max(score, 0.70)
    return score


def _extract_json_object(text: str) -> Dict[str, Any]:
    content = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        content = fenced.group(1)
    else:
        matched = re.search(r"\{.*\}", content, re.DOTALL)
        if matched:
            content = matched.group(0)
    parsed = json.loads(content)
    return parsed if isinstance(parsed, dict) else {}


def should_cache_answer(question: str, answer: str, used_graph: bool = True, completed: bool = True) -> Tuple[bool, float]:
    normalized = normalize_question(question)
    clean_answer = str(answer or "").strip()
    if not (2 <= len(normalized) <= 80):
        return False, 0.0
    if not (20 <= len(clean_answer) <= 2000):
        return False, 0.0
    context_dependent = {"这个", "这个呢", "继续", "还有吗", "上一个", "刚才", "它呢", "再说说"}
    if normalized in context_dependent or len(normalized) <= 2 and normalized in {"继续", "还有"}:
        return False, 0.0
    if re.search(r"(1[3-9]\d{9}|\d{17}[\dxX]|\w+@\w+\.\w+|密码|账号|住址|地址)", question):
        return False, 0.0
    bad_phrases = [
        "incomplete chunked read",
        "peer closed connection",
        "回答生成中断",
        "未找到相关信息",
        "暂时无法回答",
        "系统异常",
        "请稍后重试",
    ]
    if any(phrase.lower() in clean_answer.lower() for phrase in bad_phrases):
        return False, 0.0

    score = 0.60
    if used_graph:
        score += 0.20
    if 30 <= len(clean_answer) <= 800:
        score += 0.10
    score += 0.05
    if completed:
        score += 0.05
    return score >= 0.75, min(score, 1.0)


class SharedQaCacheService:
    def __init__(self, store, redis_url: Optional[str] = None):
        self.store = store
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:16379/0")
        self._redis = None
        self._redis_disabled = False
        self._pg_seeded = False
        self._redis_seeded = False
        self._last_redis_seed_attempt_at = None

    async def lookup(self, question: str) -> Optional[Dict[str, Any]]:
        await self.ensure_seeded()
        normalized = normalize_question(question)
        if not normalized:
            return None
        digest = question_hash(normalized)

        redis_payload = await self._redis_get(digest)
        if redis_payload:
            entry_id = redis_payload.get("id")
            if entry_id:
                self.store.record_qa_cache_hit(entry_id)
            await self._redis_set(redis_payload, refresh_only=True)
            return {
                "answer": redis_payload.get("answer", ""),
                "source": "redis_exact",
                "message": "命中常用问答缓存" if redis_payload.get("answer_type") == "daily" else "命中共享问答缓存",
            }

        exact = self.store.get_qa_cache_by_hash(digest)
        if exact:
            self.store.record_qa_cache_hit(exact["id"])
            await self._redis_set(exact)
            return {
                "answer": exact["answer"],
                "source": "pg_exact",
                "message": "命中常用问答缓存" if exact.get("answer_type") == "daily" else "命中共享问答缓存",
            }

        similar = await self._find_similar(question)
        if similar:
            entry, score, verified = similar
            self.store.record_qa_cache_hit(entry["id"])
            await self._redis_set(entry)
            return {
                "answer": entry["answer"],
                "source": "pg_similar_verified" if verified else "pg_similar",
                "score": score,
                "message": "命中相似问答缓存",
            }
        return None

    async def maybe_store_generated_answer(self, question: str, answer: str, used_graph: bool = True, completed: bool = True) -> Optional[Dict[str, Any]]:
        should_cache, quality = should_cache_answer(question, answer, used_graph=used_graph, completed=completed)
        if not should_cache:
            return None
        normalized = normalize_question(question)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=PG_MEDICAL_TTL_DAYS)).isoformat()
        entry = self.store.upsert_qa_cache_entry(
            question=question.strip(),
            normalized_question=normalized,
            question_hash=question_hash(normalized),
            answer=answer.strip(),
            question_tokens=tokenize_question(normalized),
            answer_type="medical_qa",
            source="generated",
            quality_score=quality,
            expires_at=expires_at,
            is_seed=False,
            is_active=True,
        )
        if quality >= 0.85:
            await self._redis_set(entry)
        self.store.prune_qa_cache_entries()
        return entry

    async def ensure_seeded(self) -> None:
        if self._pg_seeded and self._redis_seeded:
            return
        seed_entries = []
        for question, answer in SEED_QA_PAIRS:
            normalized = normalize_question(question)
            if not self._pg_seeded:
                entry = self.store.upsert_qa_cache_entry(
                    question=question,
                    normalized_question=normalized,
                    question_hash=question_hash(normalized),
                    answer=answer,
                    question_tokens=tokenize_question(normalized),
                    answer_type="daily",
                    source="seed",
                    quality_score=1.0,
                    expires_at=None,
                    is_seed=True,
                    is_active=True,
                )
            else:
                entry = self.store.get_qa_cache_by_hash(question_hash(normalized), include_inactive=True)
            if entry:
                seed_entries.append(entry)
        self._pg_seeded = True
        if self._redis_seeded:
            return
        now = datetime.now(timezone.utc)
        if self._last_redis_seed_attempt_at and now - self._last_redis_seed_attempt_at < timedelta(seconds=30):
            return
        self._last_redis_seed_attempt_at = now
        redis_ready = False
        for entry in seed_entries:
            redis_ready = await self._redis_set(entry) or redis_ready
        self._redis_seeded = redis_ready

    async def _find_similar(self, question: str) -> Optional[Tuple[Dict[str, Any], float, bool]]:
        candidates = self.store.list_qa_cache_candidates(limit=MAX_CANDIDATES)
        if not candidates:
            return None
        corpus_tokens = [candidate.get("question_tokens") or tokenize_question(candidate.get("question", "")) for candidate in candidates]
        scored = [(candidate, similarity_score(question, candidate, corpus_tokens)) for candidate in candidates]
        scored.sort(key=lambda item: item[1], reverse=True)
        best, score = scored[0]
        if score >= DIRECT_SIMILARITY_THRESHOLD:
            return best, score, False
        if score >= VERIFY_SIMILARITY_THRESHOLD and await self._verify_equivalent(question, best):
            return best, score, True
        return None

    async def _verify_equivalent(self, question: str, entry: Dict[str, Any]) -> bool:
        prompt = f"""
你是中医问答缓存命中判断器。请判断“当前问题”和“历史问题”是否在询问同一个可复用答案的问题。
只返回严格 JSON，不要输出 Markdown。

当前问题：{question}
历史问题：{entry.get("question", "")}
历史答案：{entry.get("answer", "")}

        返回格式：
{{"same_question": true, "confidence": 0.92, "reason": "简短原因"}}
"""
        try:
            from langchain_core.messages import HumanMessage

            from common.llm import llm_ainvoke

            response = await llm_ainvoke([HumanMessage(content=prompt)])
            parsed = _extract_json_object(getattr(response, "content", response))
            return bool(parsed.get("same_question")) and float(parsed.get("confidence") or 0) >= VERIFY_CONFIDENCE_THRESHOLD
        except Exception:
            return False

    async def _redis_client(self):
        if self._redis_disabled:
            return None
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            return self._redis
        except Exception:
            self._redis = None
            return None

    async def _redis_get(self, digest: str) -> Optional[Dict[str, Any]]:
        client = await self._redis_client()
        if not client:
            return None
        try:
            raw = await client.get(self._redis_key(digest))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _redis_set(self, entry: Dict[str, Any], refresh_only: bool = False) -> bool:
        client = await self._redis_client()
        if not client or not entry:
            return False
        answer_type = entry.get("answer_type") or "medical_qa"
        ttl = REDIS_DAILY_TTL_SECONDS if answer_type == "daily" else REDIS_MEDICAL_TTL_SECONDS
        payload = {
            "id": entry.get("id"),
            "question": entry.get("question"),
            "normalized_question": entry.get("normalized_question"),
            "question_hash": entry.get("question_hash"),
            "answer": entry.get("answer"),
            "answer_type": answer_type,
            "quality_score": entry.get("quality_score", 0),
        }
        try:
            if refresh_only and payload.get("question_hash"):
                await client.expire(self._redis_key(payload["question_hash"]), ttl)
            else:
                await client.set(self._redis_key(payload["question_hash"]), json.dumps(payload, ensure_ascii=False), ex=ttl)
            return True
        except Exception:
            return False

    def _redis_key(self, digest: str) -> str:
        return f"qa_cache:exact:{digest}"
