import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from common.config import Config
from __005__fastapi.__003__msg_queue import put_done_to_msg, msg_queue_manager
from __005__fastapi.app.services.auth_service import AuthError, AuthService
from __005__fastapi.app.services.graph_service import build_knowledge_graph
from __005__fastapi.app.services.knowledge_import_service import (
    FormulaNotFoundError,
    build_preview_graph,
    delete_formula_from_neo4j,
    extract_herb_knowledge,
    import_knowledge_to_neo4j,
    parse_document_text,
    summarize_source_text,
)
from __005__fastapi.app.services.search_service import build_search_results
from common.neo4j_manager import neo4j_client
from common.pg_memory_store import get_memory_store


# 这里集中暴露认证、问答、检索、图谱和方药管理相关 HTTP 接口。
def get_frontend_origins():
    defaults = ["http://localhost:3010", "http://127.0.0.1:3010"]
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


class ChatJobRequest(BaseModel):
    input: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)


class KnowledgeImportRequest(BaseModel):
    job_id: str = ""
    extracted: Dict[str, Any]


class KnowledgeDeleteRequest(BaseModel):
    name: str = Field(..., min_length=1)


@app.on_event("startup")
async def warmup_runtime_models():
    try:
        await asyncio.to_thread(memory_store.init_schema)
    except Exception as exc:
        print(f"数据库结构检查失败: {exc}")

    try:
        from common.tcm_entity_extractor import extract_tcm_entities

        await asyncio.to_thread(extract_tcm_entities, "模型预热")
    except Exception as exc:
        print(f"实体抽取模型预热失败: {exc}")

    try:
        from common.embedding_model import embedding_model
        from __004__langgraph_more_nodes.nodes import match_entity_from_neo4j_node as match_node

        await asyncio.to_thread(embedding_model.encode, ["模型预热"], convert_to_numpy=True)
        if getattr(match_node, "zhongyi_index", None) is None:
            match_node.zhongyi_index = await asyncio.to_thread(match_node.load_index)
        if getattr(match_node, "zhongyi_id2text", None) is None:
            match_node.zhongyi_id2text = await asyncio.to_thread(match_node.load_id2text)
    except Exception as exc:
        print(f"FAISS/embedding 预热失败: {exc}")


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


@app.post("/api/admin/knowledge/extract")
async def admin_extract_knowledge(
    authorization: str = Header(default=""),
    text: str = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
):
    admin = require_admin(authorization)
    source_type = "text"
    file_name = ""
    source_text = text.strip()
    try:
        if file and file.filename:
            source_type = "file"
            file_name = file.filename
            source_text = parse_document_text(file.filename, await file.read())
        if not source_text:
            raise ValueError("请输入文本或上传 txt、md、pdf、docx 文档。")
        extracted = await asyncio.to_thread(extract_herb_knowledge, source_text)
        preview_graph = build_preview_graph(extracted)
        return {
            "extracted": extracted,
            "preview_graph": preview_graph,
            "source": {
                "source_type": source_type,
                "file_name": file_name,
                "summary": summarize_source_text(source_text),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc


@app.post("/api/admin/knowledge/import")
async def admin_import_knowledge(request: KnowledgeImportRequest, authorization: str = Header(default="")):
    admin = require_admin(authorization)
    try:
        result = await asyncio.to_thread(import_knowledge_to_neo4j, neo4j_client, request.extracted)
        herb = request.extracted.get("herb", {}) if isinstance(request.extracted, dict) else {}
        job = memory_store.create_knowledge_operation_record(
            admin["id"],
            "add",
            herb.get("name", ""),
            request.extracted,
            source_type="manual",
            source_summary=summarize_source_text(json.dumps(request.extracted, ensure_ascii=False)),
        )
        return {"status": "ok", "result": result, "job": job}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/knowledge/delete")
async def admin_delete_knowledge(request: KnowledgeDeleteRequest, authorization: str = Header(default="")):
    admin = require_admin(authorization)
    try:
        result = await asyncio.to_thread(delete_formula_from_neo4j, neo4j_client, request.name)
        job = memory_store.create_knowledge_operation_record(
            admin["id"],
            "delete",
            result.get("name") or request.name,
            {"deleted": result},
            source_type="manual",
            source_summary=f"删除方药：{result.get('name') or request.name}",
        )
        return {"status": "ok", "result": result, "job": job}
    except FormulaNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc), "suggestions": exc.suggestions},
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/knowledge/imports")
async def admin_knowledge_imports(authorization: str = Header(default=""), limit: int = Query(50, ge=1, le=200)):
    admin = require_admin(authorization)
    return {"items": memory_store.list_knowledge_import_jobs(admin["id"], limit=limit)}


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


def _run_legacy_zhongyi_task_in_worker(input_text, graph_thread_id):
    asyncio.run(_legacy_zhongyi_task(input_text, graph_thread_id))


def stream_event(event_type: str, msg: str = "", progress=None, job_id=None, thread_id=None):
    payload = {"type": event_type}
    if msg:
        payload["msg"] = msg
    if progress is not None:
        payload["progress"] = max(0, min(100, int(progress)))
    if job_id:
        payload["job_id"] = job_id
    if thread_id:
        payload["thread_id"] = thread_id
    return json.dumps(payload, ensure_ascii=False) + "\n"


CHAT_STREAM_ERROR_MESSAGE = "回答生成中断，请稍后重试。"


def infer_progress_from_thought(message: str):
    text = str(message or "")
    rules = [
        (("\u5b8c\u6210", "\u57fa\u4e8e\u77e5\u8bc6\u56fe\u8c31", "\u56de\u7b54"), 98),
        (("\u5f00\u59cb", "\u57fa\u4e8e\u77e5\u8bc6\u56fe\u8c31", "\u56de\u7b54"), 90),
        (("\u5b8c\u6210", "Cypher", "\u6267\u884c"), 88),
        (("\u5f00\u59cb", "Cypher", "\u6267\u884c"), 84),
        (("\u5b8c\u6210", "Cypher", "\u67e5\u8be2"), 80),
        (("\u5f00\u59cb", "Cypher", "\u67e5\u8be2"), 72),
        (("\u5b8c\u6210", "\u5339\u914d", "\u77e5\u8bc6\u56fe\u8c31"), 66),
        (("\u5f00\u59cb", "\u5339\u914d", "\u77e5\u8bc6\u56fe\u8c31"), 58),
        (("\u5b8c\u6210", "\u5b9e\u4f53", "\u62bd\u53d6"), 52),
        (("\u5f00\u59cb", "\u5b9e\u4f53", "\u62bd\u53d6"), 44),
        (("\u5b8c\u6210", "\u4e2d\u533b\u610f\u56fe"), 40),
        (("\u5f00\u59cb", "\u8bc6\u522b", "\u4e2d\u533b\u610f\u56fe"), 32),
        (("\u5b8c\u6210", "\u8bed\u4e49", "\u8f6c\u5199"), 24),
        (("\u5f00\u59cb", "\u8bed\u4e49", "\u8f6c\u5199"), 14),
    ]
    for keywords, progress in rules:
        if all(keyword in text for keyword in keywords):
            return progress
    return None


async def generate_job_stream(input_text, user, thread_id=None, job_id=None):
    user_id = user["id"]
    session_id = user.get("session_id")
    graph_thread_id = job_id or thread_id or user_id
    assistant_chunks = []
    thoughts = []

    if job_id:
        memory_store.update_chat_job(user_id, job_id, status="running", progress=1)

    memory_store.append_chat_message(user_id, session_id, "user", input_text, thread_id=thread_id)
    quick_answer = quick_chat_answer(input_text)
    if quick_answer:
        thought = "识别为日常寒暄，直接生成回答"
        thoughts.append(thought)
        yield stream_event("think", f"{thought}\n", 60, job_id=job_id, thread_id=thread_id)
        yield stream_event("stream", quick_answer, 95, job_id=job_id, thread_id=thread_id)
        yield stream_event("done", progress=100, job_id=job_id, thread_id=thread_id)
        memory_store.append_chat_message(user_id, session_id, "assistant", quick_answer, thread_id=thread_id)
        if job_id:
            memory_store.update_chat_job(
                user_id,
                job_id,
                status="done",
                progress=100,
                thoughts="\n".join(thoughts),
                answer=quick_answer,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        return

    thought = "进入默认图谱推理链路"
    thoughts.append(thought)
    yield stream_event("think", f"{thought}\n", 8, job_id=job_id, thread_id=thread_id)
    msg_queue = msg_queue_manager.get_msg_queue_by_user_id(graph_thread_id)
    task = asyncio.create_task(asyncio.to_thread(_run_legacy_zhongyi_task_in_worker, input_text, graph_thread_id))

    try:
        while True:
            get_msg_task = asyncio.create_task(msg_queue.get())
            done_tasks, _ = await asyncio.wait({get_msg_task, task}, return_when=asyncio.FIRST_COMPLETED)
            if task in done_tasks and get_msg_task not in done_tasks:
                if msg_queue.empty():
                    get_msg_task.cancel()
                    await task
                    break
                msg = await get_msg_task
            else:
                msg = get_msg_task.result()
            if msg.get("type") == "stream":
                assistant_chunks.append(msg.get("msg", ""))
            if msg.get("type") == "think" and "progress" not in msg:
                inferred_progress = infer_progress_from_thought(msg.get("msg", ""))
                if inferred_progress is not None:
                    msg["progress"] = inferred_progress
            if job_id:
                msg["job_id"] = job_id
            if thread_id:
                msg["thread_id"] = thread_id
            if msg.get("type") == "think":
                thoughts.append(msg.get("msg", "").strip())
            progress = int(msg.get("progress") or 0)
            if job_id and progress:
                memory_store.update_chat_job(user_id, job_id, progress=progress, thoughts="\n".join(thoughts))
            yield json.dumps(msg, ensure_ascii=False) + "\n"
            if msg.get("type") == "done":
                msg_queue_manager.delete_msg_queue_by_user_id(graph_thread_id)
                break
            if task.done():
                await task

        await task
        assistant_message = "".join(assistant_chunks).strip()
        if assistant_message:
            memory_store.append_chat_message(user_id, session_id, "assistant", assistant_message, thread_id=thread_id)
        if job_id:
            memory_store.update_chat_job(
                user_id,
                job_id,
                status="done",
                progress=100,
                thoughts="\n".join(thoughts),
                answer=assistant_message,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
    except asyncio.CancelledError:
        task.cancel()
        msg_queue_manager.delete_msg_queue_by_user_id(graph_thread_id)
        if job_id:
            memory_store.update_chat_job(
                user_id,
                job_id,
                status="cancelled",
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        raise
    except Exception as exc:
        msg_queue_manager.delete_msg_queue_by_user_id(graph_thread_id)
        if job_id:
            memory_store.update_chat_job(
                user_id,
                job_id,
                status="failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        yield stream_event("error", CHAT_STREAM_ERROR_MESSAGE, 100, job_id=job_id, thread_id=thread_id)


async def generate_legacy_stream(input_text, user, thread_id=None):
    async for item in generate_job_stream(input_text, user, thread_id):
        yield item


def quick_chat_answer(input_text: str):
    normalized = "".join(str(input_text or "").strip().lower().split())
    normalized = normalized.strip("，。！？!?~～,.")
    if normalized in {"你好", "您好", "hello", "hi", "嗨", "在吗", "在嘛"}:
        return "您好，请问您有什么中医相关的问题需要咨询？"
    if normalized in {"你是谁", "你是什么", "介绍一下你", "你能做什么", "你会做什么"}:
        return "我是中医知识图谱问答助手，可以围绕方剂、药材、功效、主治、禁忌和关联图谱进行解释。"
    if normalized in {"谢谢", "感谢", "多谢", "辛苦了"}:
        return "不客气，您可以继续问我方剂、药材或症状相关问题。"
    if normalized in {"再见", "拜拜", "bye", "goodbye"}:
        return "再见，祝您一切顺利。"
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
    return StreamingResponse(generate_job_stream(input_text, user, thread_id), media_type="application/x-ndjson")


@app.post("/api/chat/jobs")
async def create_chat_job(request: ChatJobRequest, authorization: str = Header(default="")):
    user = require_user(authorization)
    thread = require_thread(user["id"], request.thread_id)
    memory_store.cancel_active_chat_jobs(user["id"], thread["id"])
    job = memory_store.create_chat_job(user["id"], user.get("session_id"), thread["id"], request.input)
    return StreamingResponse(
        generate_job_stream(request.input, user, thread["id"], job["id"]),
        media_type="application/x-ndjson",
    )


@app.get("/api/chat/jobs/{job_id}")
async def get_chat_job(job_id: str, authorization: str = Header(default="")):
    user = require_user(authorization)
    job = memory_store.get_chat_job(user["id"], job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Chat job not found.")
    return {"job": job}


@app.post("/api/chat/jobs/{job_id}/cancel")
async def cancel_chat_job(job_id: str, authorization: str = Header(default="")):
    user = require_user(authorization)
    job = memory_store.get_chat_job(user["id"], job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Chat job not found.")
    memory_store.update_chat_job(
        user["id"],
        job_id,
        status="cancelled",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    msg_queue_manager.delete_msg_queue_by_user_id(job_id)
    return {"job": memory_store.get_chat_job(user["id"], job_id)}


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
