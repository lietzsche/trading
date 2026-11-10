"""
test_adversarial_chal2.py
=========================
Adversarial Empirical Challenge Suite 2:
- Route Whitelist Security (Whitelist enforcement, profile & market-sell status, legacy AI/US route blocking)
- Auto-Orders Reconcile State Machine (PENDING / UNKNOWN transitions, >=2m timeout, mismatched identifiers, provider errors)
- Dashboard safety contract & unresolved_orders schema audit
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-characters")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

from app import main
from app.trading import TradingEngine
from tests.test_e2e_ma40_suite import InMemoryTestDB


@pytest.fixture
def mock_app_chal2():
    db = InMemoryTestDB()
    db.seed_default_operator()

    engine = TradingEngine(db, "http://mock-calc:8000", False)
    engine.now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    orig_db = main.db
    orig_engine = main.engine

    main.db = db
    main.engine = engine
    engine.db = db

    main.app.dependency_overrides.clear()
    client = TestClient(main.app, base_url="http://testserver")

    yield {"client": client, "db": db, "engine": engine}

    main.app.dependency_overrides.clear()
    main.db = orig_db
    main.engine = orig_engine


def set_auth(role="MASTER", login_id="operator", user_id=1):
    user = {
        "id": user_id,
        "user_login_id": login_id,
        "user_name": "Test User",
        "user_role": role,
        "user_email": f"{login_id}@example.com",
        "user_phone": "010-0000-0000",
        "session_version": 1,
    }
    main.app.dependency_overrides[main.current_user] = lambda: user
    if role == "MASTER":
        main.app.dependency_overrides[main.master_user] = lambda: user
    else:
        # Let master_user dependency check run naturally so it can raise 403
        if main.master_user in main.app.dependency_overrides:
            del main.app.dependency_overrides[main.master_user]


def clear_auth():
    main.app.dependency_overrides.clear()


# ==============================================================================
# SECTION 1: Route Whitelist Security & Edge Cases
# ==============================================================================

def test_route_whitelist_profile_and_market_sell_exist(mock_app_chal2):
    """Verify restored routes /api/profile and /api/upbit/orders/market-sell exist in whitelist."""
    assert "/api/profile" in main._MA40_API_PATHS
    assert "/api/upbit/orders/market-sell" in main._MA40_API_PATHS

    route_paths = [r.path for r in main.app.routes]
    assert "/api/profile" in route_paths
    assert "/api/upbit/orders/market-sell" in route_paths


def test_route_security_profile_unauthorized_and_authorized(mock_app_chal2):
    """Verify /api/profile returns 401 when unauthorized, and handles requests when authorized."""
    client = mock_app_chal2["client"]

    # 1. Unauthenticated request must return 401, NOT 404
    clear_auth()
    resp = client.put("/api/profile", json={"name": "New Name", "email": "new@test.com"})
    assert resp.status_code == 401

    # 2. Authenticated request as normal USER
    set_auth(role="USER", login_id="normal_user", user_id=2)
    resp_auth = client.put("/api/profile", json={"name": "Updated User", "email": "updated@test.com"})
    assert resp_auth.status_code == 200
    assert resp_auth.json() == {"ok": True}


def test_route_security_market_sell_rbac(mock_app_chal2):
    """Verify /api/upbit/orders/market-sell enforces authentication and MASTER RBAC."""
    client = mock_app_chal2["client"]

    # 1. Unauthenticated request -> 401
    clear_auth()
    resp = client.post("/api/upbit/orders/market-sell", json={"market": "KRW-BTC"})
    assert resp.status_code == 401

    # 2. Non-MASTER user request -> 403 Forbidden
    set_auth(role="USER", login_id="regular_user", user_id=3)
    valid_payload = {"market": "KRW-BTC", "expected_available_quantity": 0.5, "confirm": True, "keep_auto": True}
    resp_user = client.post("/api/upbit/orders/market-sell", json=valid_payload)
    assert resp_user.status_code == 403

    # 3. MASTER user request -> passes RBAC. Returns 404 (detail "등록된 Upbit 키가 없습니다."), NOT 404 route-not-found
    set_auth(role="MASTER", login_id="master_without_key", user_id=4)
    resp_master = client.post("/api/upbit/orders/market-sell", json=valid_payload)
    assert resp_master.status_code == 404
    assert "Upbit 키가 없습니다" in resp_master.json()["detail"]


@pytest.mark.parametrize("legacy_path", [
    "/api/ai/analysis",
    "/api/ai/sentiment",
    "/api/ai/recommendations",
    "/api/equities/search",
    "/api/equities/scan",
    "/api/stock/dividends",
    "/api/stock/analysis",
    "/api/admin/mail-targets",
    "/api/legacy/undefined-route",
    "/api/profile/subpath",
    "/api/upbit/orders/market-sell/extra",
])
def test_legacy_routes_strictly_blocked(mock_app_chal2, legacy_path):
    """Verify legacy dead routes and invalid subpaths are strictly blocked from execution across all HTTP methods."""
    client = mock_app_chal2["client"]
    # All HTTP methods to non-whitelisted API paths are routed to missing_api -> 404
    assert client.get(legacy_path).status_code == 404
    assert client.post(legacy_path, json={}).status_code == 404
    assert client.put(legacy_path, json={}).status_code == 404
    assert client.delete(legacy_path).status_code == 404
    assert client.patch(legacy_path, json={}).status_code == 404


# ==============================================================================
# SECTION 2: Auto-Orders Reconcile State Machine
# ==============================================================================

def test_reconcile_state_pending_to_accepted_when_confirmed_by_upbit(mock_app_chal2):
    """When Upbit confirms order execution via /v1/order, status transitions from PENDING to ACCEPTED."""
    engine = mock_app_chal2["engine"]
    db = mock_app_chal2["db"]

    key = {"id": 1, "user_login_id": "operator", "access_key": "k", "secret_key": "s"}
    ident = "auto-test-order-1"
    now_utc = datetime.now(timezone.utc)

    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-BTC",
        "side": "bid",
        "status": "PENDING",
        "created_at": now_utc,
        "updated_at": now_utc,
    })

    def mock_private(method, path, k, params=None):
        if path == "/v1/order" and params.get("identifier") == ident:
            return {
                "uuid": "upbit-uuid-111",
                "identifier": ident,
                "market": "KRW-BTC",
                "side": "bid",
                "ord_type": "price",
                "price": "50000000",
                "state": "done",
                "created_at": now_utc.isoformat(),
                "volume": None,
                "remaining_volume": None,
                "executed_volume": "0.01",
                "trades_count": 1,
            }
        raise RuntimeError("Unexpected Upbit call")

    engine.private_for_key = mock_private

    result = engine.reconcile_auto_orders(key)

    assert result == {"accepted": 1, "rejected": 0, "blocked": 0}

    req = next(r for r in db.auto_order_requests if r["identifier"] == ident)
    assert req["status"] == "ACCEPTED"

    history = next((h for h in db.order_history if h["uuid"] == "upbit-uuid-111"), None)
    assert history is not None
    assert history["login_id"] == "operator"


def test_reconcile_state_pending_retains_blocked_on_mismatched_identifier(mock_app_chal2):
    """If Upbit returns an order with mismatched identifier or market, reconcile marks it BLOCKED."""
    engine = mock_app_chal2["engine"]
    db = mock_app_chal2["db"]
    key = {"id": 1, "user_login_id": "operator"}
    ident = "auto-test-mismatch"

    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-BTC",
        "side": "bid",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc),
    })

    engine.private_for_key = lambda m, p, k, params=None: {
        "uuid": "upbit-uuid-222",
        "identifier": "DIFFERENT-IDENTIFIER",
        "market": "KRW-BTC",
    }

    result = engine.reconcile_auto_orders(key)
    assert result == {"accepted": 0, "rejected": 0, "blocked": 1}

    req = next(r for r in db.auto_order_requests if r["identifier"] == ident)
    assert req["status"] == "PENDING"


def test_reconcile_state_under_2m_remains_blocked(mock_app_chal2):
    """When order is missing in Upbit (< 2 minutes old), reconcile keeps it PENDING and BLOCKED."""
    engine = mock_app_chal2["engine"]
    db = mock_app_chal2["db"]
    key = {"id": 1, "user_login_id": "operator"}
    ident = "auto-test-fresh-missing"

    created_time = datetime.now(timezone.utc) - timedelta(seconds=60)
    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-BTC",
        "side": "bid",
        "status": "PENDING",
        "created_at": created_time,
    })

    resp = httpx.Response(404, request=httpx.Request("GET", "http://test"))
    engine.private_for_key = MagicMock(side_effect=httpx.HTTPStatusError("Not found", request=resp.request, response=resp))

    result = engine.reconcile_auto_orders(key)
    assert result == {"accepted": 0, "rejected": 0, "blocked": 1}

    req = next(r for r in db.auto_order_requests if r["identifier"] == ident)
    assert req["status"] == "PENDING"


def test_reconcile_state_over_2m_transitions_to_rejected(mock_app_chal2):
    """When order is missing in Upbit (>= 2 minutes old), reconcile transitions it to REJECTED."""
    engine = mock_app_chal2["engine"]
    db = mock_app_chal2["db"]
    key = {"id": 1, "user_login_id": "operator"}
    ident = "auto-test-aged-missing"

    created_time = datetime.now(timezone.utc) - timedelta(seconds=125)
    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-BTC",
        "side": "bid",
        "status": "PENDING",
        "created_at": created_time,
    })

    resp = httpx.Response(404, request=httpx.Request("GET", "http://test"))
    engine.private_for_key = MagicMock(side_effect=httpx.HTTPStatusError("Not found", request=resp.request, response=resp))

    result = engine.reconcile_auto_orders(key)
    assert result == {"accepted": 0, "rejected": 1, "blocked": 0}

    req = next(r for r in db.auto_order_requests if r["identifier"] == ident)
    assert req["status"] == "REJECTED"


def test_reconcile_unknown_status_over_2m_rejected(mock_app_chal2):
    """Orders with UNKNOWN status aged >= 2 minutes missing in Upbit transition to REJECTED."""
    engine = mock_app_chal2["engine"]
    db = mock_app_chal2["db"]
    key = {"id": 1, "user_login_id": "operator"}
    ident = "auto-test-unknown-status"

    created_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-ETH",
        "side": "ask",
        "status": "UNKNOWN",
        "created_at": created_time,
    })

    resp = httpx.Response(400, json={"error": {"name": "order_not_found"}}, request=httpx.Request("GET", "http://test"))
    engine.private_for_key = MagicMock(side_effect=httpx.HTTPStatusError("Bad request", request=resp.request, response=resp))

    result = engine.reconcile_auto_orders(key)
    assert result == {"accepted": 0, "rejected": 1, "blocked": 0}

    req = next(r for r in db.auto_order_requests if r["identifier"] == ident)
    assert req["status"] == "REJECTED"


def test_reconcile_server_error_retains_blocked(mock_app_chal2):
    """When Upbit returns 500 error, reconcile must NOT assume missing; it marks BLOCKED."""
    engine = mock_app_chal2["engine"]
    db = mock_app_chal2["db"]
    key = {"id": 1, "user_login_id": "operator"}
    ident = "auto-test-server-err"

    created_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-BTC",
        "side": "bid",
        "status": "PENDING",
        "created_at": created_time,
    })

    resp = httpx.Response(500, request=httpx.Request("GET", "http://test"))
    engine.private_for_key = MagicMock(side_effect=httpx.HTTPStatusError("Server Error", request=resp.request, response=resp))

    result = engine.reconcile_auto_orders(key)
    assert result == {"accepted": 0, "rejected": 0, "blocked": 1}

    req = next(r for r in db.auto_order_requests if r["identifier"] == ident)
    assert req["status"] == "PENDING"


def test_reconcile_endpoint_rbac_and_execution(mock_app_chal2):
    """Verify /api/upbit/auto-orders/reconcile RBAC: 401 unauth, 403 USER, 200 MASTER."""
    client = mock_app_chal2["client"]
    engine = mock_app_chal2["engine"]

    # 1. Unauthenticated -> 401
    clear_auth()
    resp_unauth = client.post("/api/upbit/auto-orders/reconcile")
    assert resp_unauth.status_code == 401

    # 2. USER role -> 403
    set_auth(role="USER", login_id="normal_trader", user_id=10)
    resp_user = client.post("/api/upbit/auto-orders/reconcile")
    assert resp_user.status_code == 403

    # 3. MASTER role -> 200
    set_auth(role="MASTER", login_id="super_operator", user_id=11)
    mock_app_chal2["db"].upbit_keys.append({
        "id": 99,
        "user_login_id": "super_operator",
        "access_key": "k",
        "secret_key": "s",
        "auto_on": True,
    })
    engine.reconcile_only = MagicMock(return_value={"accepted": 2, "rejected": 1, "blocked": 0})

    resp_master = client.post("/api/upbit/auto-orders/reconcile")
    assert resp_master.status_code == 200
    assert resp_master.json() == {"accepted": 2, "rejected": 1, "blocked": 0}


# ==============================================================================
# SECTION 3: Dashboard Safety Contract & Unresolved Orders Schema Audit
# ==============================================================================

def test_dashboard_safety_unresolved_orders_type_contract(mock_app_chal2):
    """
    Contract Test: Audit safety.unresolved_orders returned by GET /api/dashboard.
    Backend returns a LIST of order dicts.
    """
    db = mock_app_chal2["db"]
    client = mock_app_chal2["client"]
    engine = mock_app_chal2["engine"]

    engine.account_snapshot = lambda *args: {
        "total_valuation": 1000000.0,
        "valuation_complete": True,
        "unpriced_currencies": [],
        "assets": [{"currency": "KRW", "balance": "1000000", "locked": "0", "valuation": 1000000.0}],
    }

    now_utc = datetime.now(timezone.utc)
    db.auto_order_requests.append({
        "identifier": "unresolved-order-abc",
        "key_id": 1,
        "login_id": "operator",
        "market": "KRW-BTC",
        "side": "bid",
        "status": "PENDING",
        "created_at": now_utc,
    })

    set_auth(role="MASTER", login_id="operator", user_id=1)
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    safety = data.get("safety", {})
    assert safety.get("level") == "blocked"
    unresolved = safety.get("unresolved_orders")

    # In backend (app/main.py:649), safety.unresolved_orders is a LIST of rows
    assert isinstance(unresolved, list), f"Expected list from backend, got {type(unresolved)}"
    assert len(unresolved) == 1
    assert unresolved[0]["identifier"] == "unresolved-order-abc"
    assert safety.get("unresolved_count") == 1


def test_defensive_nulls_last_sorting_in_sql_queries():
    """Verify both recommendation and auto-order disparity queries defensively include NULLS LAST."""
    import inspect
    from app import main, trading
    main_src = inspect.getsource(main.dashboard)
    assert "DESC NULLS LAST, u.id DESC" in main_src
    trading_src = inspect.getsource(trading.TradingEngine._auto_order)
    assert "DESC NULLS LAST," in trading_src


@pytest.mark.parametrize("method", ["get", "post", "put", "delete", "patch", "head"])
def test_unmapped_routes_all_methods_return_404(mock_app_chal2, method):
    """Ensure unmapped /api and unknown routes return 404 for all HTTP methods."""
    client = mock_app_chal2["client"]
    caller = getattr(client, method)
    r1 = caller("/api/nonexistent-endpoint")
    assert r1.status_code == 404
    r2 = caller("/api")
    assert r2.status_code == 404

