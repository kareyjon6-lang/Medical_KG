from __005__fastapi.app.services.auth_service import AuthService
from common.pg_memory_store import PgMemoryStore


def test_auth_service_registers_logs_in_and_resolves_bearer_token(tmp_path):
    store = PgMemoryStore(f"sqlite:///{tmp_path / 'auth.db'}")
    store.init_schema()
    auth = AuthService(store)

    session = auth.register("alice", "secret123")

    assert session["user"]["username"] == "alice"
    assert session["token"]
    assert auth.current_user(f"Bearer {session['token']}")["username"] == "alice"

    login = auth.login("alice", "secret123")
    assert auth.current_user(f"Bearer {login['token']}")["id"] == session["user"]["id"]
