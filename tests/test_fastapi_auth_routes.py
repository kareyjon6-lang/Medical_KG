import importlib

import pytest

from __005__fastapi.__003__msg_queue import put_done_to_msg, put_stream_text_to_msg

TestClient = pytest.importorskip("fastapi.testclient").TestClient


def load_main_with_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    module = importlib.import_module("__005__fastapi.app.main")
    return importlib.reload(module)


def test_process_requires_authenticated_user_id(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.post("/process", json={"input": "你好", "user_id": "attacker"})

    assert response.status_code == 401


def test_process_stream_stores_chat_history(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)

    async def fake_legacy_task(input_text, user_id):
        assert input_text == "麻黄汤的组成是什么？"
        await put_stream_text_to_msg(user_id, "麻黄汤由麻黄、桂枝、杏仁、甘草组成。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
    monkeypatch.setattr(main, "graph_direct_answer", lambda input_text: None)
    auth = client.post("/api/auth/register", json={"username": "stream_user", "password": "secret123"}).json()

    response = client.post(
        "/process",
        json={"input": "麻黄汤的组成是什么？"},
        headers={"Authorization": f"Bearer {auth['token']}"},
    )

    assert response.status_code == 200
    assert '"type": "stream"' in response.text

    history = client.get(
        "/api/chat/history",
        headers={"Authorization": f"Bearer {auth['token']}"},
    ).json()["items"]

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "麻黄汤的组成是什么？"
    assert history[1]["content"] == "麻黄汤由麻黄、桂枝、杏仁、甘草组成。"


def test_process_uses_fast_greeting_path_without_graph(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)

    async def should_not_run(input_text, user_id):
        raise AssertionError("simple greetings should not call the LangGraph workflow")

    monkeypatch.setattr(main, "_legacy_zhongyi_task", should_not_run)
    auth = client.post("/api/auth/register", json={"username": "hello_user", "password": "secret123"}).json()

    response = client.post(
        "/process",
        json={"input": "你好"},
        headers={"Authorization": f"Bearer {auth['token']}"},
    )

    assert response.status_code == 200
    assert "您好，请问您有什么中医相关的问题需要咨询？" in response.text

    history = client.get(
        "/api/chat/history",
        headers={"Authorization": f"Bearer {auth['token']}"},
    ).json()["items"]

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "你好"
    assert history[1]["content"] == "您好，请问您有什么中医相关的问题需要咨询？"


def test_process_uses_graph_direct_answer_for_formula_fields(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)

    class FakeNeo4j:
        def run_cypher(self, query, parameters=None):
            assert parameters["query"] == "麻黄汤"
            return [
                {
                    "properties": {
                        "name": "麻黄汤",
                        "ingredients": "麻黄、桂枝、杏仁、甘草",
                        "source": "伤寒论",
                    },
                    "label": "Formula",
                    "related_items": [
                        {"type": "HAS_INGREDIENT", "label": "Herb", "properties": {"name": "麻黄"}},
                        {"type": "HAS_INGREDIENT", "label": "Herb", "properties": {"name": "桂枝"}},
                    ],
                }
            ]

    async def should_not_run(input_text, user_id):
        raise AssertionError("formula field questions should use graph direct answer")

    monkeypatch.setattr(main, "neo4j_client", FakeNeo4j())
    monkeypatch.setattr(main, "_legacy_zhongyi_task", should_not_run)
    auth = client.post("/api/auth/register", json={"username": "formula_user", "password": "secret123"}).json()

    response = client.post(
        "/process",
        json={"input": "麻黄汤的组成是什么？"},
        headers={"Authorization": f"Bearer {auth['token']}"},
    )

    assert response.status_code == 200
    assert "麻黄汤的组成如下" in response.text
    assert "麻黄、桂枝、杏仁、甘草" in response.text
    assert "Cypher查询" in response.text


def test_chat_thread_routes_and_process_thread_storage(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)
    seen_graph_thread_ids = []

    async def fake_legacy_task(input_text, user_id):
        seen_graph_thread_ids.append(user_id)
        await put_stream_text_to_msg(user_id, "麻黄汤禁忌包括表虚自汗。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
    monkeypatch.setattr(main, "graph_direct_answer", lambda input_text: None)
    auth = client.post("/api/auth/register", json={"username": "thread_user", "password": "secret123"}).json()
    headers = {"Authorization": f"Bearer {auth['token']}"}

    created = client.post(
        "/api/chat/threads",
        json={"title": "麻黄汤禁忌", "focus_entity": "麻黄汤"},
        headers=headers,
    )
    assert created.status_code == 200
    thread_id = created.json()["thread"]["id"]

    stream_response = client.post(
        "/process",
        json={"input": "麻黄汤有什么禁忌？", "thread_id": thread_id},
        headers=headers,
    )
    assert stream_response.status_code == 200
    assert seen_graph_thread_ids == [thread_id]

    threads = client.get("/api/chat/threads", headers=headers).json()["items"]
    assert threads[0]["id"] == thread_id
    assert threads[0]["message_count"] == 2
    assert threads[0]["focus_entity"] == "麻黄汤"

    messages = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).json()["items"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "麻黄汤有什么禁忌？"
    assert messages[1]["content"] == "麻黄汤禁忌包括表虚自汗。"


def test_cors_origins_include_deployed_frontend_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://tcm.example.com, https://www.tcm.example.com")
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://tcm.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == "https://tcm.example.com"
