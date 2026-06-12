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


def test_process_uses_default_langgraph_for_formula_fields(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)
    seen_graph_thread_ids = []

    async def fake_legacy_task(input_text, user_id):
        seen_graph_thread_ids.append(user_id)
        await put_stream_text_to_msg(user_id, "默认图谱推理回答。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
    auth = client.post("/api/auth/register", json={"username": "formula_user", "password": "secret123"}).json()

    response = client.post(
        "/process",
        json={"input": "麻黄汤的组成是什么？"},
        headers={"Authorization": f"Bearer {auth['token']}"},
    )

    assert response.status_code == 200
    assert seen_graph_thread_ids == [auth["user"]["id"]]
    assert "默认图谱推理回答" in response.text


def test_process_has_no_fast_graph_shortcut_for_symptom_questions(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)
    seen_inputs = []

    async def fake_legacy_task(input_text, user_id):
        seen_inputs.append(input_text)
        await put_stream_text_to_msg(user_id, "已进入默认图谱链路。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
    auth = client.post("/api/auth/register", json={"username": "fast_user", "password": "secret123"}).json()

    response = client.post(
        "/process",
        json={"input": "肚子疼应该吃什么药？"},
        headers={"Authorization": f"Bearer {auth['token']}"},
    )

    assert response.status_code == 200
    assert seen_inputs == ["肚子疼应该吃什么药？"]
    assert "已进入默认图谱链路" in response.text

    history = client.get(
        "/api/chat/history",
        headers={"Authorization": f"Bearer {auth['token']}"},
    ).json()["items"]

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[1]["content"] == "已进入默认图谱链路。"


def test_chat_thread_routes_and_process_thread_storage(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)
    seen_graph_thread_ids = []

    async def fake_legacy_task(input_text, user_id):
        seen_graph_thread_ids.append(user_id)
        await put_stream_text_to_msg(user_id, "麻黄汤禁忌包括表虚自汗。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
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


def test_chat_job_endpoint_uses_job_id_as_graph_queue_key(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)
    seen_graph_thread_ids = []

    async def fake_legacy_task(input_text, user_id):
        seen_graph_thread_ids.append(user_id)
        await put_stream_text_to_msg(user_id, "job 隔离回答。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
    auth = client.post("/api/auth/register", json={"username": "job_user", "password": "secret123"}).json()
    headers = {"Authorization": f"Bearer {auth['token']}"}
    thread = client.post("/api/chat/threads", json={"title": "job 测试"}, headers=headers).json()["thread"]

    response = client.post(
        "/api/chat/jobs",
        json={"input": "麻黄汤是什么？", "thread_id": thread["id"]},
        headers=headers,
    )

    assert response.status_code == 200
    assert "job 隔离回答" in response.text
    job_id = response.text.split('"job_id": "')[1].split('"', 1)[0]
    assert seen_graph_thread_ids == [job_id]
    assert job_id != thread["id"]
    job = client.get(f"/api/chat/jobs/{job_id}", headers=headers).json()["job"]
    assert job["thread_id"] == thread["id"]
    assert job["status"] == "done"


def test_same_thread_new_job_cancels_previous_active_job_but_other_threads_keep_running(monkeypatch, tmp_path):
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)
    auth = client.post("/api/auth/register", json={"username": "parallel_user", "password": "secret123"}).json()
    headers = {"Authorization": f"Bearer {auth['token']}"}
    first_thread = client.post("/api/chat/threads", json={"title": "一号"}, headers=headers).json()["thread"]
    second_thread = client.post("/api/chat/threads", json={"title": "二号"}, headers=headers).json()["thread"]

    first_job = main.memory_store.create_chat_job(auth["user"]["id"], auth["session_id"], first_thread["id"], "第一个问题")
    main.memory_store.update_chat_job(auth["user"]["id"], first_job["id"], status="running")
    second_job = main.memory_store.create_chat_job(auth["user"]["id"], auth["session_id"], second_thread["id"], "第二个问题")
    main.memory_store.update_chat_job(auth["user"]["id"], second_job["id"], status="running")

    async def fake_legacy_task(input_text, user_id):
        await put_stream_text_to_msg(user_id, "新问题回答。")
        await put_done_to_msg(user_id)

    monkeypatch.setattr(main, "_legacy_zhongyi_task", fake_legacy_task)
    response = client.post(
        "/api/chat/jobs",
        json={"input": "同一历史对话的新问题", "thread_id": first_thread["id"]},
        headers=headers,
    )

    assert response.status_code == 200
    assert main.memory_store.get_chat_job(auth["user"]["id"], first_job["id"])["status"] == "cancelled"
    assert main.memory_store.get_chat_job(auth["user"]["id"], second_job["id"])["status"] == "running"


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


def test_admin_login_and_user_management_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("TCM_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("TCM_ADMIN_PASSWORD", "admin123")
    main = load_main_with_sqlite(monkeypatch, tmp_path)
    client = TestClient(main.app)

    ordinary = client.post("/api/auth/register", json={"username": "ordinary_user", "password": "secret123"}).json()
    ordinary_headers = {"Authorization": f"Bearer {ordinary['token']}"}
    assert client.get("/api/admin/users", headers=ordinary_headers).status_code == 403

    failed_admin = client.post("/api/auth/admin/login", json={"username": "ordinary_user", "password": "secret123"})
    assert failed_admin.status_code == 401

    admin = client.post("/api/auth/admin/login", json={"username": "admin", "password": "admin123"})
    assert admin.status_code == 200
    assert admin.json()["user"]["role"] == "admin"
    admin_headers = {"Authorization": f"Bearer {admin.json()['token']}"}

    created = client.post(
        "/api/admin/users",
        json={"username": "created_by_admin", "password": "secret123", "role": "user"},
        headers=admin_headers,
    )
    assert created.status_code == 200
    created_user = created.json()["user"]
    assert created_user["role"] == "user"

    users = client.get("/api/admin/users", headers=admin_headers).json()["items"]
    assert any(item["username"] == "created_by_admin" for item in users)

    assert client.delete(f"/api/admin/users/{created_user['id']}", headers=admin_headers).status_code == 200
    users_after_delete = client.get("/api/admin/users", headers=admin_headers).json()["items"]
    assert not any(item["username"] == "created_by_admin" for item in users_after_delete)

    admin_id = admin.json()["user"]["id"]
    assert client.delete(f"/api/admin/users/{admin_id}", headers=admin_headers).status_code == 400
