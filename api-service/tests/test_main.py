import os
import httpx
import pytest

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


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolate_requests(monkeypatch):
    client.cookies.clear()
    main.app.dependency_overrides.clear()
    monkeypatch.setattr(main, "db", FakeDatabase())
    monkeypatch.setattr(main.engine, "record_error", lambda *args: None)
    yield
    main.app.dependency_overrides.clear()


def authenticated(role="MASTER"):
    user = {"id": 1, "user_login_id": "master", "user_name": "Master", "user_role": role, "user_phone": "010-0000-0000"}
    main.app.dependency_overrides[main.current_user] = lambda: user
    return user


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


@pytest.mark.parametrize("endpoint", ["settings", "system", "errors", "users", "autos", "mail-targets"])
def test_regular_user_cannot_read_admin_pages(endpoint):
    authenticated("USER")
    assert client.get(f"/api/admin/{endpoint}").status_code == 403


@pytest.mark.parametrize("role, expected", [("USER", 403), ("ADMIN", 200), ("MASTER", 200)])
def test_error_log_roles(role, expected):
    authenticated(role)
    assert client.get("/api/admin/errors").status_code == expected


def test_admin_cannot_run_order_job_or_change_user():
    authenticated("ADMIN")
    assert client.post("/api/admin/jobs/auto-order").status_code == 403
    assert client.put("/api/admin/users/2", json={"user_role": "MASTER"}).status_code == 403


@pytest.mark.parametrize("field, value", [
    ("expected_high_percentage", 0), ("expected_low_percentage", -100),
    ("expected_low_percentage", 10), ("highest_price_reference_days", 2),
    ("highest_price_reference_days", 201),
])
def test_invalid_calculation_setting_is_rejected(field, value):
    authenticated()
    payload = {"expected_high_percentage": 10, "expected_low_percentage": -5,
               "highest_price_reference_days": 60, "volume_check": False, field: value}
    assert client.put("/api/admin/settings/upbit", json=payload).status_code == 422


def test_missing_setting_is_not_reported_as_saved():
    authenticated()
    payload = {"expected_high_percentage": 10, "expected_low_percentage": -5,
               "highest_price_reference_days": 60, "volume_check": False}
    assert client.put("/api/admin/settings/upbit", json=payload).status_code == 404


def test_valid_setting_is_saved(monkeypatch):
    authenticated()
    calls = []
    monkeypatch.setattr(main.db, "one", lambda *args: {"id": 1})
    monkeypatch.setattr(main.db, "execute", lambda *args: calls.append(args))
    payload = {"expected_high_percentage": 10, "expected_low_percentage": -5,
               "highest_price_reference_days": 60, "volume_check": False}
    assert client.put("/api/admin/settings/upbit", json=payload).status_code == 200
    assert calls[0][1] == (10, -5, 60, False, "upbit")


@pytest.mark.parametrize("calculation_up, expected", [(True, 200), (False, 503)])
def test_health_status_reflects_dependency_failure(monkeypatch, calculation_up, expected):
    monkeypatch.setattr(main.httpx, "get", lambda *a, **kw: type("R", (), {"is_success": calculation_up})())
    result = client.get("/api/health")
    assert result.status_code == expected
    assert result.json()["calculation"] == ("UP" if calculation_up else "DOWN")


def test_health_database_failure_returns_503(monkeypatch):
    monkeypatch.setattr(main.db, "one", lambda *args: None)
    monkeypatch.setattr(main.httpx, "get", lambda *a, **kw: type("R", (), {"is_success": True})())
    assert client.get("/api/health").status_code == 503


def test_unknown_api_returns_json_404_and_is_not_cached():
    result = client.get("/api/not-a-real-route")
    assert result.status_code == 404
    assert result.headers["content-type"].startswith("application/json")
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("password", ["a" * 73, "가" * 25])
def test_passwords_beyond_bcrypt_byte_limit_rejected(password):
    assert client.post("/api/auth/join", json={"login_id": "test", "name": "Test", "password": password}).status_code == 422
    authenticated()
    assert client.put("/api/profile", json={"name": "Test", "password": password}).status_code == 422


def test_profile_does_not_erase_omitted_phone(monkeypatch):
    authenticated()
    calls = []
    monkeypatch.setattr(main.db, "execute", lambda *args: calls.append(args))
    assert client.put("/api/profile", json={"name": "Test", "email": None}).status_code == 200
    assert calls[0][1][2] == "010-0000-0000"


@pytest.mark.parametrize("status, path, disabled", [(401, "/v1/accounts", True), (429, "/v1/accounts", False), (403, "/v1/ticker/all", False)])
def test_account_errors_only_disable_auto_for_private_auth_failure(monkeypatch, status, path, disabled):
    authenticated()
    writes = []
    monkeypatch.setattr(main.db, "one", lambda *args: {"id": 1, "access_key": "test", "secret_key": "test"})
    monkeypatch.setattr(main.db, "execute", lambda *args: writes.append(args))
    def fail(*args):
        request = httpx.Request("GET", f"https://api.upbit.com{path}")
        httpx.Response(status, request=request).raise_for_status()
    monkeypatch.setattr(main.engine, "account_snapshot", fail)
    assert client.get("/api/upbit/accounts").status_code == 502
    assert bool(writes) == disabled


def test_account_connection_failure_returns_helpful_error_without_disabling_auto(monkeypatch):
    authenticated()
    writes = []
    monkeypatch.setattr(main.db, "one", lambda *args: {"id": 1, "access_key": "test", "secret_key": "test"})
    monkeypatch.setattr(main.db, "execute", lambda *args: writes.append(args))
    def fail(*args):
        raise httpx.ConnectError("temporary failure")
    monkeypatch.setattr(main.engine, "account_snapshot", fail)
    assert client.get("/api/upbit/accounts").status_code == 502
    assert not writes


def test_recommendation_balance_failure_means_unknown_not_unowned(monkeypatch):
    authenticated()
    monkeypatch.setattr(main.db, "one", lambda *args: {"access_key": "test", "secret_key": "test"})
    monkeypatch.setattr(main.db, "all", lambda *args: [{"code": "KRW-BTC"}])
    def fail(*args):
        raise httpx.ConnectError("temporary failure")
    monkeypatch.setattr(main.engine, "private_upbit", fail)
    result = client.get("/api/recommendations/upbit")
    assert result.status_code == 200
    assert result.json()[0]["owned"] is None


def test_user_deactivation_disables_auto_in_same_statement(monkeypatch):
    authenticated()
    calls = []
    monkeypatch.setattr(main.db, "one", lambda *args: {"user_login_id": "other", "user_role": "USER"})
    monkeypatch.setattr(main.db, "execute", lambda *args: calls.append(args))
    assert client.put("/api/admin/users/2", json={"user_role": "USER", "deleted": True}).status_code == 200
    assert len(calls) == 1
    assert "UPDATE tb_upbit_key SET auto_on=false" in calls[0][0]
    assert calls[0][1] == ("USER", True, 2)


def test_master_cannot_disable_self():
    # FakeDatabase has no target by id, so provide it without touching the real DB.
    actor = authenticated()
    original = main.db.one
    main.db.one = lambda *args: actor
    try:
        assert client.put("/api/admin/users/1", json={"user_role": "MASTER", "deleted": True}).status_code == 400
    finally:
        main.db.one = original


@pytest.mark.parametrize("result, expected", [({"status": "ERROR"}, 502), ({"status": "PARTIAL"}, 502), ({"status": "SKIPPED"}, 409), ({"status": "OK"}, 200), (None, 200)])
def test_manual_job_status_is_not_falsely_reported_successful(monkeypatch, result, expected):
    authenticated()
    monkeypatch.setattr(main.engine, "auto_order", lambda: result)
    assert client.post("/api/admin/jobs/auto-order").status_code == expected
