import os

os.environ.setdefault("SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-characters")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

from fastapi.testclient import TestClient
from app import main


class FakeDatabase:
    def one(self, query, params=()):
        if "SELECT 1" in query:
            return {"?column?": 1}
        if "user_password" in query:
            import bcrypt
            return {"user_login_id": "master", "user_name": "Master", "user_role": "MASTER", "user_password": bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()}
        if "FROM tb_user WHERE user_login_id" in query:
            return {"id": 1, "user_login_id": "master", "user_name": "Master", "user_role": "MASTER", "user_email": None}
        if "count(*)" in query:
            return {"count": 0}
        return None

    def all(self, query, params=()):
        return []

    def execute(self, query, params=()):
        return None

    def executemany(self, query, params):
        return None


main.db = FakeDatabase()
client = TestClient(main.app)


def test_protected_endpoint_requires_login():
    assert client.get("/api/admin/system").status_code == 401


def test_login_and_admin_access(monkeypatch):
    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: type("R", (), {"is_success": True})())
    response = client.post("/api/auth/login", json={"login_id": "master", "password": "password123"})
    assert response.status_code == 200
    result = client.get("/api/admin/system")
    assert result.status_code == 200
    assert result.json()["trading_execution"] == "DISABLED"
    assert result.json()["scheduler_running"] is False


def test_wrong_password_is_rejected():
    assert client.post("/api/auth/login", json={"login_id": "master", "password": "wrong"}).status_code == 401
