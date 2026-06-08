from typing import Optional

from common.pg_memory_store import PgMemoryStore


class AuthError(ValueError):
    pass


class AuthService:
    def __init__(self, store: PgMemoryStore):
        self.store = store
        self.store.init_schema()

    def register(self, username: str, password: str):
        user = self.store.create_user(username, password)
        session = self.store.create_session(user["id"])
        return {"token": session["token"], "session_id": session["id"], "user": user}

    def login(self, username: str, password: str):
        user = self.store.verify_user(username, password)
        if not user:
            raise AuthError("Invalid username or password.")
        session = self.store.create_session(user["id"])
        return {"token": session["token"], "session_id": session["id"], "user": user}

    def current_user(self, authorization: Optional[str]):
        token = bearer_token(authorization)
        if not token:
            raise AuthError("Missing bearer token.")
        user = self.store.get_user_by_token(token)
        if not user:
            raise AuthError("Invalid bearer token.")
        return user

    def logout(self, authorization: Optional[str]) -> None:
        token = bearer_token(authorization)
        if token:
            self.store.revoke_session(token)


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    return token or None
