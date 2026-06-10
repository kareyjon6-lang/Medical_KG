import asyncio
import json
import os
import re

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from common.config import Config
from __005__fastapi.__003__msg_queue import put_done_to_msg, msg_queue_manager
from __005__fastapi.app.services.auth_service import AuthError, AuthService
from __005__fastapi.app.services.graph_service import build_knowledge_graph
from __005__fastapi.app.services.search_service import build_search_results
from common.neo4j_manager import neo4j_client
from common.pg_memory_store import get_memory_store


def get_frontend_origins():
    defaults = ["http://localhost:3000", "http://127.0.0.1:3000"]
    configured = os.getenv("FRONTEND_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return defaults + origins


Config()
app = FastAPI(title="中医知识图谱接口", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_frontend_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
memory_store = get_memory_store()
auth_service = AuthService(memory_store)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=2)
    password: str = Field(..., min_length=6)


class AdminUserRequest(BaseModel):
    username: str = Field(..., min_length=2)
    password: str = Field(..., min_length=6)
    role: str = Field(default="user")


class ChatThreadRequest(BaseModel):
    title: str = Field(default="新的对话", min_length=1)
    focus_entity: str = ""


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/auth/register")
async def register(request: AuthRequest):
    try:
        return auth_service.register(request.username, request.password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
async def login(request: AuthRequest):
    try:
        return auth_service.login(request.username, request.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/admin/login")
async def admin_login(request: AuthRequest):
    try:
        return auth_service.login_admin(request.username, request.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/auth/me")
async def me(authorization: str = Header(default="")):
    user = require_user(authorization)
    return {"user": {"id": user["id"], "username": user["username"], "role": user.get("role", "user")}}


@app.post("/api/auth/logout")
async def logout(authorization: str = Header(default="")):
    auth_service.logout(authorization)
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: str = Header(default="")):
    from __004__langgraph_more_nodes.langgraph_more_nodes import zhongyi_response

    user = require_user(authorization)
    thread_id = user["id"]
    session_id = user.get("session_id")
    memory_store.append_chat_message(user["id"], session_id, "user", request.message)
    answer = await zhongyi_response(request.message, thread_id)
    memory_store.append_chat_message(user["id"], session_id, "assistant", answer)
    return ChatResponse(answer=answer, thread_id=thread_id)


@app.get("/api/chat/history")
async def chat_history(
    authorization: str = Header(default=""),
    limit: int = Query(30, ge=1, le=100),
):
    user = require_user(authorization)
    return {"items": memory_store.get_chat_history(user["id"], limit=limit)}


@app.get("/api/chat/threads")
async def chat_threads(
    authorization: str = Header(default=""),
    limit: int = Query(30, ge=1, le=100),
):
    user = require_user(authorization)
    return {"items": memory_store.get_chat_threads(user["id"], limit=limit)}


@app.post("/api/chat/threads")
async def create_chat_thread(request: ChatThreadRequest, authorization: str = Header(default="")):
    user = require_user(authorization)
    thread = memory_store.create_chat_thread(user["id"], request.title, request.focus_entity)
    return {"thread": thread}


@app.get("/api/chat/threads/{thread_id}/messages")
async def chat_thread_messages(
    thread_id: str,
    authorization: str = Header(default=""),
    limit: int = Query(100, ge=1, le=200),
):
    user = require_user(authorization)
    require_thread(user["id"], thread_id)
    return {"items": memory_store.get_thread_messages(user["id"], thread_id, limit=limit)}


@app.delete("/api/chat/threads/{thread_id}/messages")
async def clear_chat_thread_messages(thread_id: str, authorization: str = Header(default="")):
    user = require_user(authorization)
    require_thread(user["id"], thread_id)
    deleted = memory_store.clear_thread_messages(user["id"], thread_id)
    return {"status": "ok", "deleted": deleted}


@app.delete("/api/chat/threads/{thread_id}")
async def delete_chat_thread(thread_id: str, authorization: str = Header(default="")):
    user = require_user(authorization)
    if not memory_store.delete_chat_thread(user["id"], thread_id):
        raise HTTPException(status_code=404, detail="Chat thread not found.")
    return {"status": "ok"}


@app.get("/api/memory")
async def memory(authorization: str = Header(default=""), limit: int = Query(20, ge=1, le=100)):
    user = require_user(authorization)
    return {"items": memory_store.get_memories(user["id"], limit=limit)}


@app.get("/api/admin/users")
async def admin_users(authorization: str = Header(default=""), limit: int = Query(100, ge=1, le=500)):
    require_admin(authorization)
    return {"items": memory_store.list_users(limit=limit)}


@app.post("/api/admin/users")
async def admin_create_user(request: AdminUserRequest, authorization: str = Header(default="")):
    require_admin(authorization)
    try:
        user = memory_store.create_user(request.username, request.password, role=request.role)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: str, authorization: str = Header(default="")):
    admin = require_admin(authorization)
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Current administrator cannot be deleted.")
    target = next((item for item in memory_store.list_users(limit=500) if item["id"] == user_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.get("role") == "admin" and memory_store.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="At least one administrator is required.")
    if not memory_store.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"status": "ok"}


@app.get("/api/search")
async def search(
    q: str = Query(default=""),
    limit: int = Query(200, ge=1, le=1000),
    label: str = Query(default=""),
    source: str = Query(default=""),
    effects: str = Query(default=""),
):
    effect_filters = [item.strip() for item in effects.split("|") if item.strip()]
    return {"items": build_search_results(neo4j_client, q, limit=limit, label=label, source=source, effects=effect_filters)}


@app.get("/api/graph")
async def graph(
    q: str = Query(..., min_length=1),
    depth: int = Query(1, ge=1, le=2),
    limit: int = Query(30, ge=1, le=100),
):
    return build_knowledge_graph(neo4j_client, q, depth=depth, limit=limit)


async def _legacy_zhongyi_task(input_text, graph_thread_id):
    from __004__langgraph_more_nodes.langgraph_more_nodes import zhongyi_response

    await zhongyi_response(input_text, graph_thread_id)
    await put_done_to_msg(graph_thread_id)


def graph_direct_answer(input_text: str):
    text = str(input_text or "").strip()
    if not text:
        return None

    intent_map = [
        ("ingredients", ("组成", "成分", "药物", "药材", "由什么", "有哪些药")),
        ("effect", ("功效", "作用", "效用")),
        ("indication", ("主治", "治疗", "适合", "症状", "病症")),
        ("usage", ("用法", "服法", "怎么服", "如何服")),
        ("taboo", ("禁忌", "注意", "不适合", "慎用")),
        ("source", ("出处", "来源", "出自")),
    ]
    requested_keys = [key for key, markers in intent_map if any(marker in text for marker in markers)]
    if not requested_keys:
        return None

    entity = extract_formula_query(text)
    if not entity:
        return None

    selected = load_formula_for_direct_answer(entity)
    if not selected:
        return None

    props = selected.get("properties") or {}
    pieces = []
    for key in requested_keys:
        value = props.get(key)
        if value:
            pieces.append(f"{public_property_label(key)}：{value}")

    if not pieces:
        return None

    name = selected.get("name") or entity
    answer = f"{name}的{public_intent_summary(requested_keys)}如下：\n" + "\n".join(f"- {piece}" for piece in pieces)
    thoughts = [
        f"识别到方剂实体：{name}",
        f"命中知识图谱字段：{public_intent_summary(requested_keys)}",
        f"Cypher查询：MATCH (f:Formula)-[r]-(n) WHERE f.name CONTAINS '{name}' RETURN f,r,n LIMIT 80",
        "已根据图谱属性和关联节点生成回答",
    ]
    return {"answer": answer, "thoughts": thoughts}



def load_formula_for_direct_answer(entity: str):
    query = """
    MATCH (f:Formula)
    WHERE f.name = $query OR toLower(f.name) CONTAINS toLower($query)
    OPTIONAL MATCH (f)-[:HAS_INGREDIENT]-(herb:Herb)
    WITH f, collect(DISTINCT herb.name) AS ingredient_names
    ORDER BY CASE WHEN f.name = $query THEN 0 ELSE 1 END, f.name
    RETURN properties(f) AS properties,
           head(labels(f)) AS label,
           ingredient_names
    LIMIT 1
    """
    try:
        records = neo4j_client.run_cypher(query, {"query": entity})
    except Exception:
        records = []
    if records:
        record = records[0]
        props = dict(record.get("properties") or {})
        ingredient_names = [name for name in (record.get("ingredient_names") or []) if name]
        if ingredient_names and not props.get("ingredients"):
            props["ingredients"] = "\u3001".join(ingredient_names)
        return {
            "name": props.get("name") or entity,
            "label": record.get("label") or "Formula",
            "properties": {key: value for key, value in props.items() if value not in (None, "")},
        }

    results = build_search_results(neo4j_client, entity, limit=5, label="Formula")
    if not results:
        return None
    return next((item for item in results if item.get("name") == entity), results[0])


def extract_formula_query(text: str):
    cleaned = re.sub(r"[\uff0c\u3002\uff01\uff1f\uff1b\uff1a\u3001,.!?;:]", " ", text)
    suffixes = "\u6c64\u4e38\u6563\u996e\u818f\u4e39\u5242\u65b9\u714e"
    candidates = re.findall(r"[\u4e00-\u9fff]{2,12}[" + suffixes + r"]", cleaned)
    if candidates:
        return candidates[0]
    for marker in ("\u7684", "\u662f", "\u6709", "\u7531"):
        if marker in cleaned:
            head = cleaned.split(marker, 1)[0].strip()
            if 1 < len(head) <= 12:
                return head
    return ""

def related_names_for(related: str, prefix: str):
    names = []
    for part in re.split(r"[\uff1b;]", str(related or "")):
        if prefix not in part:
            continue
        cleaned = re.sub(r"^.*?[\uff1a:]", "", part)
        cleaned = re.sub(r"[\uff08(].*?[\uff09)]", "", cleaned).strip()
        if cleaned:
            names.append(cleaned)
    return list(dict.fromkeys(names))


def public_property_label(key: str):
    return {
        "source": "出处",
        "ingredients": "组成",
        "effect": "功效",
        "usage": "用法",
        "taboo": "禁忌",
        "indication": "主治",
    }.get(key, key)


def public_intent_summary(keys):
    labels = [public_property_label(key) for key in keys]
    return "、".join(labels)


def chunk_text(text: str, size: int = 18):
    clean = str(text or "")
    for index in range(0, len(clean), max(1, size)):
        yield clean[index:index + size]


async def generate_legacy_stream(input_text, user, thread_id=None):
    user_id = user["id"]
    session_id = user.get("session_id")
    graph_thread_id = thread_id or user_id
    assistant_chunks = []
    memory_store.append_chat_message(user_id, session_id, "user", input_text, thread_id=thread_id)
    quick_answer = quick_chat_answer(input_text)
    if quick_answer:
        yield json.dumps({"type": "think", "msg": "识别为日常寒暄，直接生成问候回复  \n"}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "stream", "msg": quick_answer}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"
        memory_store.append_chat_message(user_id, session_id, "assistant", quick_answer, thread_id=thread_id)
        return

    direct_answer = graph_direct_answer(input_text)
    if direct_answer:
        for thought in direct_answer["thoughts"]:
            yield json.dumps({"type": "think", "msg": f"{thought}\n"}, ensure_ascii=False) + "\n"
        for chunk in chunk_text(direct_answer["answer"], 80):
            yield json.dumps({"type": "stream", "msg": chunk}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"
        memory_store.append_chat_message(user_id, session_id, "assistant", direct_answer["answer"], thread_id=thread_id)
        return

    task = asyncio.create_task(_legacy_zhongyi_task(input_text, graph_thread_id))

    while True:
        msg_queue = msg_queue_manager.get_msg_queue_by_user_id(graph_thread_id)
        msg = await msg_queue.get()
        if msg.get("type") == "stream":
            assistant_chunks.append(msg.get("msg", ""))
        yield json.dumps(msg, ensure_ascii=False) + "\n"
        if msg.get("type") == "done":
            msg_queue_manager.delete_msg_queue_by_user_id(graph_thread_id)
            break

    await task
    assistant_message = "".join(assistant_chunks).strip()
    if assistant_message:
        memory_store.append_chat_message(user_id, session_id, "assistant", assistant_message, thread_id=thread_id)


def quick_chat_answer(input_text: str):
    normalized = "".join(str(input_text or "").strip().lower().split())
    normalized = normalized.strip("，。！？!?~～,.")
    if normalized in {"你好", "您好", "hello", "hi", "嗨", "在吗", "在嘛"}:
        return "您好，请问您有什么中医相关的问题需要咨询？"
    return ""


@app.post("/process")
async def process(data: dict, authorization: str = Header(default="")):
    user = require_user(authorization)
    input_text = data.get("input", "")
    thread_id = (data.get("thread_id") or "").strip() or None
    if thread_id:
        require_thread(user["id"], thread_id)
    quick_answer = quick_chat_answer(input_text)
    if quick_answer:
        session_id = user.get("session_id")
        memory_store.append_chat_message(user["id"], session_id, "user", input_text, thread_id=thread_id)
        memory_store.append_chat_message(user["id"], session_id, "assistant", quick_answer, thread_id=thread_id)
        payload = "\n".join([
            json.dumps({"type": "think", "msg": "识别为日常寒暄，直接生成问候回复  \n"}, ensure_ascii=False),
            json.dumps({"type": "stream", "msg": quick_answer}, ensure_ascii=False),
            json.dumps({"type": "done"}, ensure_ascii=False),
            "",
        ])
        return Response(content=payload, media_type="application/x-ndjson")
    return StreamingResponse(generate_legacy_stream(input_text, user, thread_id), media_type="application/x-ndjson")


def require_user(authorization: str):
    try:
        return auth_service.current_user(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_admin(authorization: str):
    user = require_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator permission required.")
    return user


def require_thread(user_id: str, thread_id: str):
    thread = memory_store.get_chat_thread(user_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Chat thread not found.")
    return thread


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
