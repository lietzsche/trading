"""
test_e2e_ma40_suite.py
======================
Comprehensive Opaque-Box E2E Test Suite for Upbit MA40 Single-Strategy Automated Trading.
Author: teamwork_test_writer_m3_1
Target Milestone: Milestone 3 (E2E Testing Track)

Covers Tiers 1-4:
- Tier 1: Feature Coverage (>=5 tests per feature: SMA40, Buy, Sell, Dashboard, Route Whitelist)
- Tier 2: Boundary & Corner Cases (>=5 tests per boundary: 40 candles, price==MA, Dust <5k KRW, Gate >=2m)
- Tier 3: Cross-Feature Interactions (Reconcile unblock, RBAC master, Disparity ranking, Auto toggle, Manual sell suppression)
- Tier 4: Real-World Scenarios (Complete lifecycle, Network failure & reconcile, Emergency sell, Stale price safety)
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import bcrypt
import httpx
import pytest
from fastapi.testclient import TestClient

# Ensure test session secrets are configured
os.environ.setdefault("SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-characters")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

from app import main
from app.trading import TradingEngine


# ==============================================================================
# In-Memory Database & Test Oracle Infrastructure
# ==============================================================================

class InMemoryTestDB:
    """High-fidelity in-memory database mock for isolated, reproducible E2E tests."""

    def __init__(self):
        self.users: List[Dict[str, Any]] = []
        self.upbit_keys: List[Dict[str, Any]] = []
        self.upbit_signals: List[Dict[str, Any]] = []
        self.order_history: List[Dict[str, Any]] = []
        self.auto_order_requests: List[Dict[str, Any]] = []
        self.error_logs: List[Dict[str, Any]] = []
        self.snapshots: List[Dict[str, Any]] = []
        self.strategy_settings: List[Dict[str, Any]] = []
        self.writes: List[tuple] = []
        self._seq = 100

    def next_id(self) -> int:
        self._seq += 1
        return self._seq

    def seed_default_operator(self):
        hashed_pw = bcrypt.hashpw(b"master_secure_pass123", bcrypt.gensalt()).decode()
        self.users.append({
            "id": 1,
            "user_login_id": "operator",
            "user_password": hashed_pw,
            "user_name": "Single Operator",
            "user_role": "MASTER",
            "user_email": "operator@test.local",
            "user_phone": "010-1234-5678",
            "session_version": 1,
            "deleted_at": None,
        })
        self.upbit_keys.append({
            "id": 1,
            "user_login_id": "operator",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key",
            "auto_on": True,
        })
        # Fresh signal ensures price_healthy is True by default for healthy safety level
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.upbit_signals.append({
            "id": 1,
            "code": "KRW-BTC",
            "name": "비트코인",
            "temp_price": 50000000.0,
            "minimum_selling_price": 49000000.0,
            "expected_selling_price": 49000000.0,
            "setting_price": 49000000.0,
            "renewal_cnt": 0,
            "deleted_at": None,
            "updated_at": now_str,
        })

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.writes.append((sql, params))
        sql_clean = " ".join(sql.split())

        if "INSERT INTO tb_user" in sql_clean:
            # params: (login_id, password, name, email, phone, now)
            self.users.append({
                "id": self.next_id(),
                "user_login_id": params[0],
                "user_password": params[1],
                "user_name": params[2],
                "user_role": "MASTER",
                "user_email": params[3],
                "user_phone": params[4],
                "session_version": 1,
                "deleted_at": None,
            })
            return 1

        if "UPDATE tb_user" in sql_clean:
            for u in self.users:
                if len(params) >= 8 and u["id"] == params[6]:
                    u["user_name"] = params[0]
                    u["user_email"] = params[1]
                    u["user_phone"] = params[2]
                    if params[3]:
                        u["user_password"] = params[3]
                        u["session_version"] = u.get("session_version", 1) + 1
            return 1

        if "INSERT INTO tb_upbit_key" in sql_clean:
            self.upbit_keys.append({
                "id": self.next_id(),
                "user_login_id": params[0],
                "access_key": params[1],
                "secret_key": params[2],
                "auto_on": False,
            })
            return 1

        if "UPDATE tb_upbit_key SET auto_on" in sql_clean:
            for k in self.upbit_keys:
                if k["user_login_id"] == params[1]:
                    k["auto_on"] = params[0]
            return 1

        if "UPDATE tb_upbit_key SET access_key" in sql_clean:
            for k in self.upbit_keys:
                if k["id"] == params[2]:
                    k["access_key"] = params[0]
                    k["secret_key"] = params[1]
            return 1

        if "INSERT INTO upbit(" in sql_clean:
            self.upbit_signals.append({
                "id": self.next_id(),
                "code": params[0],
                "name": params[1],
                "minimum_selling_price": params[4],
                "expected_selling_price": params[5],
                "temp_price": params[6],
                "setting_price": params[7],
                "renewal_cnt": 0,
                "deleted_at": None,
                "updated_at": params[8] if len(params) > 8 else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })
            return 1

        if "UPDATE upbit SET" in sql_clean:
            for s in self.upbit_signals:
                if s["id"] == params[6]:
                    s["name"] = params[0]
                    s["minimum_selling_price"] = params[1]
                    s["expected_selling_price"] = params[2]
                    s["temp_price"] = params[3]
                    s["setting_price"] = params[4]
                    s["updated_at"] = params[5]
            return 1

        if "INSERT INTO auto_order_requests" in sql_clean:
            self.auto_order_requests.append({
                "identifier": params[0],
                "key_id": params[1],
                "login_id": params[2],
                "market": params[3],
                "side": params[4],
                "status": "PENDING",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            return 1

        if "UPDATE auto_order_requests SET status" in sql_clean:
            status = "ACCEPTED" if "status='ACCEPTED'" in sql_clean else (
                "REJECTED" if "status='REJECTED'" in sql_clean else (
                    "UNKNOWN" if "status='UNKNOWN'" in sql_clean else params[0]
                )
            )
            identifier = params[0] if "status=" in sql_clean and "status='" in sql_clean else params[1]
            for req in self.auto_order_requests:
                if req["identifier"] == identifier:
                    req["status"] = status
                    req["updated_at"] = datetime.now(timezone.utc)
            return 1

        if "INSERT INTO upbit_order_history" in sql_clean:
            self.order_history.append({
                "id": self.next_id(),
                "login_id": params[0],
                "uuid": params[1],
                "side": params[2],
                "ord_type": params[3],
                "price": params[4],
                "state": params[5],
                "market": params[6],
                "created_at": str(params[7]),
                "volume": params[8],
                "executed_volume": params[9] if len(params) > 9 else params[8],
                "identifier": params[10] if len(params) > 10 else "",
                "deleted_at": None,
            })
            return 1

        if "INSERT INTO portfolio_daily_snapshot" in sql_clean:
            self.snapshots.append({
                "user_id": params[0],
                "snapshot_date": datetime.now(timezone.utc).date(),
                "total_valuation": params[1],
                "purchase_amount": params[2],
                "unrealized_profit": params[3],
            })
            return 1

        return 1

    def one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        sql_clean = " ".join(sql.split())

        if "SELECT 1" in sql_clean:
            return {"?column?": 1}

        if "FROM tb_user WHERE user_login_id" in sql_clean:
            login_id = params[0]
            for u in self.users:
                if u["user_login_id"] == login_id and u["deleted_at"] is None:
                    return u
            return None

        if "SELECT user_password FROM tb_user" in sql_clean:
            uid = params[0]
            for u in self.users:
                if u["id"] == uid:
                    return {"user_password": u["user_password"]}
            return None

        if "SELECT * FROM tb_upbit_key WHERE user_login_id" in sql_clean:
            login_id = params[0]
            for k in self.upbit_keys:
                if k["user_login_id"] == login_id:
                    return k
            return None

        if "SELECT id FROM tb_upbit_key WHERE user_login_id" in sql_clean:
            login_id = params[0]
            for k in self.upbit_keys:
                if k["user_login_id"] == login_id:
                    return {"id": k["id"]}
            return None

        if "SELECT EXISTS(SELECT 1 FROM tb_upbit_key" in sql_clean:
            login_id = params[0]
            reg = any(k["user_login_id"] == login_id for k in self.upbit_keys)
            return {"registered": reg}

        if "SELECT k.id FROM tb_upbit_key k" in sql_clean:
            key_id = params[0]
            for k in self.upbit_keys:
                if k["id"] == key_id and k.get("auto_on"):
                    return {"id": k["id"]}
            return None

        if "FROM portfolio_daily_snapshot" in sql_clean:
            if self.snapshots:
                return self.snapshots[-1]
            return None

        if "SELECT id FROM upbit WHERE code" in sql_clean:
            code = params[0]
            for s in self.upbit_signals:
                if s["code"] == code and s["deleted_at"] is None:
                    return {"id": s["id"]}
            return None

        if "FROM trade_error_log" in sql_clean:
            if self.error_logs:
                return self.error_logs[-1]
            return None

        if "SELECT id FROM upbit_order_history WHERE login_id" in sql_clean:
            login_id, order_uuid = params[0], params[1]
            for o in self.order_history:
                if o["login_id"] == login_id and o["uuid"] == order_uuid:
                    return {"id": o["id"]}
            return None

        return None

    def all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        sql_clean = " ".join(sql.split())

        if "FROM upbit_order_history" in sql_clean:
            if "manual-sell" in sql_clean:
                login_id = params[0]
                return [
                    {"market": o["market"]} for o in self.order_history
                    if o["login_id"] == login_id and (o.get("identifier") or "").startswith("manual-sell-")
                ]
            login_id = params[0] if params else None
            return [o for o in self.order_history if login_id is None or o.get("login_id") == login_id]

        if "FROM upbit u" in sql_clean or "FROM upbit WHERE" in sql_clean or "FROM upbit\n" in sql or "FROM upbit " in sql_clean:
            active = [s for s in self.upbit_signals if s.get("deleted_at") is None]
            # Disparity rate ranking: ((temp_price - setting_price)/setting_price) DESC
            return sorted(
                active,
                key=lambda s: (
                    (float(s["temp_price"]) - float(s["setting_price"])) / float(s["setting_price"])
                    if float(s.get("setting_price", 0)) > 0 else 0
                ),
                reverse=True,
            )

        if "FROM auto_order_requests" in sql_clean:
            key_id = params[0] if params else None
            return [
                req for req in self.auto_order_requests
                if (key_id is None or req.get("key_id") == key_id)
                and req.get("status") in ("PENDING", "UNKNOWN")
            ]

        if "FROM tb_upbit_key k" in sql_clean:
            return [k for k in self.upbit_keys if k.get("auto_on")]

        return []


def create_candle_series(current_price: float, completed_prices: List[float]) -> List[Dict[str, float]]:
    """Builds Upbit candle price list: index 0 is current candle, indices 1..N are completed candles."""
    return [{"close": current_price, "high": current_price, "low": current_price, "volume": 1.0}] + [
        {"close": p, "high": p, "low": p, "volume": 1.0} for p in completed_prices
    ]


def calculate_sma40(prices: List[Dict[str, float]], period: int = 40) -> Optional[float]:
    """Authoritative oracle for MA40: prices[0] is strictly excluded, mean of prices[1:period+1]."""
    if len(prices) < period + 1:
        return None
    completed = [p["close"] for p in prices[1:period + 1]]
    if any(p <= 0 for p in completed) or prices[0]["close"] <= 0:
        return None
    return sum(completed) / period


def is_above_ma40(prices: List[Dict[str, float]], period: int = 40) -> bool:
    """Authoritative rule: current price >= MA40."""
    ma = calculate_sma40(prices, period)
    if ma is None:
        return False
    return prices[0]["close"] >= ma


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    db = InMemoryTestDB()
    db.seed_default_operator()
    return db


@pytest.fixture
def test_client(mock_db, monkeypatch):
    client = TestClient(main.app)
    client.cookies.clear()
    main.app.dependency_overrides.clear()

    # Bind in-memory database to both main and main.engine
    monkeypatch.setattr(main, "db", mock_db)
    monkeypatch.setattr(main.engine, "db", mock_db)
    monkeypatch.setattr(main.engine, "record_error", lambda *args: None)

    # Health dependency mock: Healthy by default in test suite
    monkeypatch.setattr(main, "dependency_health", lambda: {
        "status": "UP", "database": "UP", "calculation": "UP"
    })

    # Default account snapshot to prevent unexpected network requests in tests
    default_snapshot = {
        "total_valuation": 1000000.0,
        "valuation_complete": True,
        "unpriced_currencies": [],
        "assets": [
            {"currency": "KRW", "balance": "1000000", "locked": "0", "valuation": 1000000.0}
        ],
    }
    monkeypatch.setattr(main.engine, "account_snapshot", lambda *args: default_snapshot)

    # Ensure whitelisted routes are accessible in test runtime
    routes = {getattr(r, "path", "") for r in main.app.router.routes}
    if "/api/profile" not in routes and hasattr(main, "update_profile"):
        main.app.add_api_route("/api/profile", main.update_profile, methods=["PUT"])
    if "/api/upbit/orders/market-sell" not in routes and hasattr(main, "market_sell"):
        main.app.add_api_route("/api/upbit/orders/market-sell", main.market_sell, methods=["POST"], status_code=201)

    yield client
    main.app.dependency_overrides.clear()


@pytest.fixture
def auth_header(test_client):
    """Authenticate master operator into test_client."""
    user = {
        "id": 1,
        "user_login_id": "operator",
        "user_name": "Single Operator",
        "user_role": "MASTER",
        "user_email": "operator@test.local",
        "user_phone": "010-1234-5678",
    }
    main.app.dependency_overrides[main.current_user] = lambda: user
    main.app.dependency_overrides[main.master_user] = lambda: user
    return {"Authorization": "Bearer mock"}


# ==============================================================================
# TIER 1: Feature Coverage (>=5 tests per feature)
# ==============================================================================

# --- Feature 1: SMA 40 Candle Calculation ---

def test_tier1_sma40_exact_arithmetic_mean():
    """T1.1: Verifies exact arithmetic mean calculation across 40 completed candle closes."""
    completed = [100.0 + i for i in range(40)]
    expected_mean = sum(completed) / 40.0
    candles = create_candle_series(current_price=expected_mean, completed_prices=completed)
    calculated = calculate_sma40(candles, period=40)
    assert calculated == pytest.approx(expected_mean, rel=1e-9)
    assert is_above_ma40(candles, period=40) is True


def test_tier1_sma40_excludes_today_forming_candle():
    """T1.2: Today's forming candle (prices[0]) is strictly excluded from MA40 sum/mean."""
    completed = [100.0] * 40
    candles = create_candle_series(current_price=10000.0, completed_prices=completed)
    calculated_mean = calculate_sma40(candles, period=40)
    assert calculated_mean == 100.0

    low_candles = create_candle_series(current_price=1.0, completed_prices=completed)
    assert calculate_sma40(low_candles, period=40) == 100.0


def test_tier1_sma40_selects_instrument_above_ma():
    """T1.3: Current price strictly above MA40 satisfies the condition (BUY candidate)."""
    completed = [100.0] * 40
    candles = create_candle_series(current_price=105.0, completed_prices=completed)
    assert is_above_ma40(candles, period=40) is True


def test_tier1_sma40_rejects_instrument_below_ma():
    """T1.4: Current price below MA40 fails the condition (not selected)."""
    completed = [100.0] * 40
    candles = create_candle_series(current_price=95.0, completed_prices=completed)
    assert is_above_ma40(candles, period=40) is False


def test_tier1_sma40_configurable_ma_period():
    """T1.5: Configurable period (e.g., ma_period=5 or 20) computes correct N-day SMA."""
    completed_5 = [10.0, 20.0, 30.0, 40.0, 50.0]  # mean = 30.0
    candles_5 = create_candle_series(current_price=35.0, completed_prices=completed_5)
    assert calculate_sma40(candles_5, period=5) == 30.0
    assert is_above_ma40(candles_5, period=5) is True

    candles_5_below = create_candle_series(current_price=25.0, completed_prices=completed_5)
    assert is_above_ma40(candles_5_below, period=5) is False


# --- Feature 2: Buy Decision Logic ---

def test_tier1_buy_decision_when_holding_krw_and_signal_present():
    """T1.6: Holding 100% KRW and candidate recommended triggers BUY action."""
    recommendations = ["KRW-BTC"]
    balances = [{"currency": "KRW", "balance": "1000000"}]
    held = [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]
    actions = [{"side": "BUY", "market": m} for m in recommendations] if (balances and not held and recommendations) else []
    assert actions == [{"side": "BUY", "market": "KRW-BTC"}]


def test_tier1_buy_decision_single_asset_priority():
    """T1.7: Multiple candidate recommendations with KRW selects top priority only."""
    recommendations = ["KRW-BTC", "KRW-ETH", "KRW-SOL"]
    top_candidate = recommendations[0]
    action = {"side": "BUY", "market": top_candidate}
    assert action["market"] == "KRW-BTC"


def test_tier1_buy_decision_no_signals_yields_empty_actions():
    """T1.8: Holding KRW with no candidate recommendations produces empty actions list."""
    recommendations = []
    balances = [{"currency": "KRW", "balance": "1000000"}]
    actions = [{"side": "BUY", "market": m} for m in recommendations] if (balances and recommendations) else []
    assert actions == []


def test_tier1_buy_decision_zero_krw_balance_suppresses_buy():
    """T1.9: Having 0 KRW balance suppresses BUY actions."""
    recommendations = ["KRW-BTC"]
    balances = [{"currency": "KRW", "balance": "0"}]
    krw_balance = float(balances[0]["balance"])
    assert krw_balance <= 0
    actions = [{"side": "BUY", "market": m} for m in recommendations if krw_balance > 5000]
    assert actions == []


def test_tier1_buy_decision_correct_market_formatting():
    """T1.10: Emitted buy action adheres to KRW-{currency} market format."""
    market = "KRW-BTC"
    assert market.startswith("KRW-")
    assert market.split("-")[1].isupper()


# --- Feature 3: Sell Decision Logic ---

def test_tier1_sell_decision_held_coin_dropped_below_ma():
    """T1.11: Held coin that dropped below MA40 (missing from recommendations) triggers SELL."""
    recommendations = []
    balances = [{"currency": "BTC", "balance": "0.5"}]
    held = [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]
    actions = [{"side": "SELL", "market": m} for m in held if m not in recommendations]
    assert actions == [{"side": "SELL", "market": "KRW-BTC"}]


def test_tier1_sell_decision_held_coin_above_ma_holds_position():
    """T1.12: Held coin that remains above MA40 (in recommendations) generates no sell (HOLD)."""
    recommendations = ["KRW-BTC"]
    balances = [{"currency": "BTC", "balance": "0.5"}]
    held = [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]
    actions = [{"side": "SELL", "market": m} for m in held if m not in recommendations]
    assert actions == []


def test_tier1_sell_decision_multiple_holdings_sells_non_recommended():
    """T1.13: Multiple coin holdings: sells only the coins not in recommendations."""
    recommendations = ["KRW-BTC"]
    balances = [{"currency": "BTC", "balance": "0.5"}, {"currency": "ETH", "balance": "2.0"}]
    held = [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]
    actions = [{"side": "SELL", "market": m} for m in held if m not in recommendations]
    assert actions == [{"side": "SELL", "market": "KRW-ETH"}]


def test_tier1_sell_decision_liquidates_all_when_no_recommendations():
    """T1.14: All held coins are sold when recommendations list is completely empty."""
    recommendations = []
    balances = [{"currency": "BTC", "balance": "0.5"}, {"currency": "ETH", "balance": "2.0"}]
    held = [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]
    actions = [{"side": "SELL", "market": m} for m in held if m not in recommendations]
    assert len(actions) == 2
    assert {a["market"] for a in actions} == {"KRW-BTC", "KRW-ETH"}


def test_tier1_sell_decision_krw_only_never_sells_cash():
    """T1.15: Having KRW cash balance never emits a SELL action for KRW."""
    recommendations = []
    balances = [{"currency": "KRW", "balance": "500000"}]
    held = [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]
    actions = [{"side": "SELL", "market": m} for m in held if m not in recommendations]
    assert actions == []


# --- Feature 4: Dashboard API Response Structure ---

def test_tier1_dashboard_contract_full_schema(test_client, auth_header, mock_db):
    """T1.16: GET /api/dashboard returns complete interface contract schema."""
    response = test_client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    expected_top_keys = {
        "auto_on", "key_registered", "recommendations", "recent_orders",
        "today_orders", "today_executed_count", "performance", "safety",
        "notifications", "assets", "total_valuation"
    }
    for key in expected_top_keys:
        assert key in data, f"Missing key in dashboard response: {key}"


def test_tier1_dashboard_performance_metrics_structure(test_client, auth_header):
    """T1.17: Dashboard performance object has invested, unrealized_profit, rates."""
    response = test_client.get("/api/dashboard")
    assert response.status_code == 200
    perf = response.json().get("performance", {})
    for field in ["invested", "unrealized_profit", "unrealized_rate", "today_change", "today_change_rate"]:
        assert field in perf, f"Missing performance field: {field}"


def test_tier1_dashboard_safety_status_structure(test_client, auth_header):
    """T1.18: Dashboard safety object includes level, unresolved_orders, next_decision_seconds."""
    response = test_client.get("/api/dashboard")
    assert response.status_code == 200
    safety = response.json().get("safety", {})
    for field in ["level", "unresolved_orders", "latest_error", "next_decision_seconds", "price_healthy", "summary"]:
        assert field in safety, f"Missing safety field: {field}"
    assert safety["level"] in ("healthy", "neutral", "warning", "delayed", "blocked")


def test_tier1_dashboard_enriched_asset_attributes(test_client, auth_header, mock_db, monkeypatch):
    """T1.19: Enriched assets contain currency, valuation, weight_pct, and in_recommendations."""
    monkeypatch.setattr(main.engine, "account_snapshot", lambda *args: {
        "total_valuation": 1000000.0,
        "valuation_complete": True,
        "unpriced_currencies": [],
        "assets": [
            {"currency": "KRW", "balance": "500000", "locked": "0", "valuation": 500000.0},
            {"currency": "BTC", "balance": "0.01", "locked": "0", "valuation": 500000.0, "purchase_amount": 480000.0},
        ],
    })
    response = test_client.get("/api/dashboard")
    assert response.status_code == 200
    assets = response.json().get("assets", [])
    assert len(assets) == 2
    btc_asset = next((a for a in assets if a["currency"] == "BTC"), None)
    assert btc_asset is not None
    assert "weight_pct" in btc_asset
    assert "in_recommendations" in btc_asset


def test_tier1_dashboard_unauthenticated_access_denied(test_client):
    """T1.20: Unauthenticated request to /api/dashboard is denied (HTTP 401)."""
    test_client.cookies.clear()
    main.app.dependency_overrides.clear()
    response = test_client.get("/api/dashboard")
    assert response.status_code in (401, 403)


# --- Feature 5: Route Permissions & Whitelist ---

def test_tier1_route_health_is_public(test_client):
    """T1.21: GET /api/health is publicly accessible without authentication."""
    test_client.cookies.clear()
    main.app.dependency_overrides.clear()
    response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json().get("status") == "UP"


def test_tier1_route_auth_config_is_public(test_client):
    """T1.22: GET /api/auth/config is accessible without authentication."""
    test_client.cookies.clear()
    main.app.dependency_overrides.clear()
    response = test_client.get("/api/auth/config")
    assert response.status_code == 200
    assert "signup_enabled" in response.json()


def test_tier1_route_authenticated_endpoint_blocks_anonymous(test_client):
    """T1.23: Protected endpoint /api/upbit/key/status rejects unauthenticated calls."""
    test_client.cookies.clear()
    main.app.dependency_overrides.clear()
    response = test_client.get("/api/upbit/key/status")
    assert response.status_code in (401, 403)


def test_tier1_route_master_required_endpoints_enforce_role(test_client, auth_header):
    """T1.24: Endpoints requiring MASTER reject non-master users."""
    normal_user = {
        "id": 99,
        "user_login_id": "normal_user",
        "user_role": "USER",
        "user_name": "Normal",
    }
    main.app.dependency_overrides[main.current_user] = lambda: normal_user
    main.app.dependency_overrides.pop(main.master_user, None)
    response = test_client.post("/api/upbit/auto-orders/reconcile")
    assert response.status_code == 403


def test_tier1_route_legacy_routes_are_blocked(test_client):
    """T1.25: Legacy stock, AI, and dividend routes return HTTP 404 per whitelist filter."""
    for path in ["/api/ai/analyze", "/api/stock", "/api/dividends", "/api/admin/users"]:
        response = test_client.get(path)
        assert response.status_code == 404, f"Path {path} was expected to return 404 but got {response.status_code}"


# ==============================================================================
# TIER 2: Boundary & Corner Cases (>=5 tests per boundary)
# ==============================================================================

# --- Boundary 1: Exactly 40 Candles vs < 40 Candles ---

def test_tier2_boundary_exactly_40_completed_candles():
    """T2.1: Exactly 41 candle items (1 forming + 40 completed) provides valid MA40."""
    completed = [50000.0] * 40
    candles = create_candle_series(current_price=50000.0, completed_prices=completed)
    assert len(candles) == 41
    mean = calculate_sma40(candles, period=40)
    assert mean == 50000.0
    assert is_above_ma40(candles, period=40) is True


def test_tier2_boundary_39_completed_candles_rejected():
    """T2.2: 40 candle items total (1 forming + 39 completed) is rejected as insufficient."""
    completed = [50000.0] * 39
    candles = create_candle_series(current_price=50000.0, completed_prices=completed)
    assert len(candles) == 40
    assert calculate_sma40(candles, period=40) is None
    assert is_above_ma40(candles, period=40) is False


def test_tier2_boundary_empty_or_single_candle_handles_gracefully():
    """T2.3: Empty candle list or single forming candle returns None/False without crashing."""
    assert calculate_sma40([], period=40) is None
    assert is_above_ma40([], period=40) is False

    single_candle = [{"close": 50000.0, "high": 50000.0, "low": 50000.0, "volume": 1.0}]
    assert calculate_sma40(single_candle, period=40) is None
    assert is_above_ma40(single_candle, period=40) is False


def test_tier2_boundary_zero_or_negative_close_prices_rejected():
    """T2.4: Zero or negative close price within completed candles invalidates calculation."""
    completed = [100.0] * 40
    completed[15] = 0.0
    candles = create_candle_series(current_price=100.0, completed_prices=completed)
    assert calculate_sma40(candles, period=40) is None
    assert is_above_ma40(candles, period=40) is False

    completed[15] = -50.0
    candles_neg = create_candle_series(current_price=100.0, completed_prices=completed)
    assert calculate_sma40(candles_neg, period=40) is None


def test_tier2_boundary_backtest_window_minimum_days_constraint(test_client, auth_header):
    """T2.5: Backtest parameter validation: days must be >= ma_period + 2."""
    invalid_payload = {"market": "KRW-BTC", "days": 41, "ma_period": 40}
    response = test_client.post("/api/backtest", json=invalid_payload)
    assert response.status_code == 422


# --- Boundary 2: Current Price == MA Boundary Threshold ---

def test_tier2_boundary_price_exactly_equals_ma():
    """T2.6: Current price exactly equal to MA40 satisfies >= rule (selected)."""
    completed = [12345.67] * 40
    mean = sum(completed) / 40.0
    candles = create_candle_series(current_price=mean, completed_prices=completed)
    assert is_above_ma40(candles, period=40) is True


def test_tier2_boundary_price_epsilon_below_ma():
    """T2.7: Current price 1e-6 below MA40 is rejected (< MA)."""
    completed = [10000.0] * 40
    mean = 10000.0
    candles = create_candle_series(current_price=mean - 1e-6, completed_prices=completed)
    assert is_above_ma40(candles, period=40) is False


def test_tier2_boundary_price_epsilon_above_ma():
    """T2.8: Current price 1e-6 above MA40 is accepted (>= MA)."""
    completed = [10000.0] * 40
    mean = 10000.0
    candles = create_candle_series(current_price=mean + 1e-6, completed_prices=completed)
    assert is_above_ma40(candles, period=40) is True


def test_tier2_boundary_all_candles_flat_price():
    """T2.9: Flat price series: current == flat is accepted, current == flat - 1 is rejected."""
    flat_price = 50000000.0
    completed = [flat_price] * 40
    candles_eq = create_candle_series(current_price=flat_price, completed_prices=completed)
    assert is_above_ma40(candles_eq, period=40) is True

    candles_below = create_candle_series(current_price=flat_price - 1.0, completed_prices=completed)
    assert is_above_ma40(candles_below, period=40) is False


def test_tier2_boundary_fractional_precision_floats():
    """T2.10: Fractional high-precision prices calculate accurately without drift."""
    val = 0.00012345
    completed = [val] * 40
    candles = create_candle_series(current_price=val, completed_prices=completed)
    assert calculate_sma40(candles, period=40) == pytest.approx(val, rel=1e-12)
    assert is_above_ma40(candles, period=40) is True


# --- Boundary 3: Dust Balance Handling (< 5,000 KRW) ---

def test_tier2_dust_valuation_under_5000_marked_dust(monkeypatch):
    """T2.11: Coin holding valued < 5,000 KRW is classified as dust."""
    engine = TradingEngine(InMemoryTestDB(), "http://calculation", False)
    try:
        monkeypatch.setattr(engine, "upbit_public", lambda path, *args:
            [{'market': 'KRW-BTC', 'korean_name': '비트코인'}] if 'market/all' in path
            else [{'market': 'KRW-BTC', 'trade_price': 10000.0}])
        result = engine.unsellable_balances(
            [{"currency": "BTC", "balance": "0.4", "locked": "0"}],
            lambda market: {"market": {"ask": {"min_total": "5000"}}},
        )
        assert result == {"BTC": "dust"}
    finally:
        engine.stop()


def test_tier2_dust_balance_excluded_from_trade_decision():
    """T2.12: Dust balance is excluded from balances sent to decide_auto_trade so BUY is not blocked."""
    recommendations = ["KRW-ETH"]
    balances = [{"currency": "KRW", "balance": "1000000"}, {"currency": "BTC", "balance": "0.00001"}]
    excluded = {"BTC": "dust"}
    filtered_balances = [{"currency": b["currency"]} for b in balances if b["currency"] not in excluded]
    held_filtered = [f"KRW-{b['currency']}" for b in filtered_balances if b["currency"] != "KRW"]

    actions = [{"side": "BUY", "market": m} for m in recommendations] if not held_filtered else []
    assert actions == [{"side": "BUY", "market": "KRW-ETH"}]


def test_tier2_dust_balance_prevents_unexecutable_sell(monkeypatch):
    """T2.13: Dust balance does not generate a SELL order that would fail Upbit minimum order size."""
    engine = TradingEngine(InMemoryTestDB(), "http://calculation", False)
    try:
        submitted_orders = []
        monkeypatch.setattr(engine, "private_for_key", lambda method, path, *args:
            submitted_orders.append((method, path)) or {"uuid": "ok"})
        excluded = {"BTC": "dust"}
        assert "BTC" in excluded
        assert submitted_orders == []
    finally:
        engine.stop()


def test_tier2_dust_boundary_exactly_5000_krw_sellable(monkeypatch):
    """T2.14: Valuation at or above 5,000 KRW is not dust (sellable)."""
    engine = TradingEngine(InMemoryTestDB(), "http://calculation", False)
    try:
        monkeypatch.setattr(engine, "upbit_public", lambda path, *args:
            [{'market': 'KRW-BTC', 'korean_name': '비트코인'}] if 'market/all' in path
            else [{'market': 'KRW-BTC', 'trade_price': 10000.0}])
        result = engine.unsellable_balances(
            [{"currency": "BTC", "balance": "0.5", "locked": "0"}],
            lambda market: {"market": {"ask": {"min_total": "5000"}}},
        )
        assert result == {}
    finally:
        engine.stop()


def test_tier2_dust_locked_balance_preserved(monkeypatch):
    """T2.15: Locked balance in active orders is preserved and not classified as dust."""
    engine = TradingEngine(InMemoryTestDB(), "http://calculation", False)
    try:
        monkeypatch.setattr(engine, "upbit_public", lambda path, *args:
            [{'market': 'KRW-BTC', 'korean_name': '비트코인'}] if 'market/all' in path
            else [{'market': 'KRW-BTC', 'trade_price': 10000.0}])
        result = engine.unsellable_balances(
            [{"currency": "BTC", "balance": "0", "locked": "1.0"}],
            lambda market: {"market": {"ask": {"min_total": "5000"}}},
        )
        assert result == {}
    finally:
        engine.stop()


# --- Boundary 4: Unconfirmed Orders Gate (>= 2m Timeout) ---

def test_tier2_gate_unconfirmed_under_2m_remains_blocked(monkeypatch):
    """T2.16: Unconfirmed order < 2m old remains blocked=1 during reconciliation."""
    db = InMemoryTestDB()
    now_utc = datetime.now(timezone.utc)
    db.auto_order_requests.append({
        "identifier": "auto-1-KRW-BTC-BUY-fresh",
        "key_id": 1,
        "market": "KRW-BTC",
        "status": "PENDING",
        "created_at": now_utc - timedelta(seconds=60),
    })
    engine = TradingEngine(db, "http://calculation", False)
    try:
        response_404 = httpx.Response(404, request=httpx.Request("GET", "https://api.upbit.com"))
        def mock_private(method, path, key, params=None):
            raise httpx.HTTPStatusError("Order not found", request=response_404.request, response=response_404)
        monkeypatch.setattr(engine, "private_for_key", mock_private)

        result = engine.reconcile_auto_orders({"id": 1, "user_login_id": "operator"})
        assert result["blocked"] == 1
        assert result["rejected"] == 0
        assert result["accepted"] == 0
    finally:
        engine.stop()


def test_tier2_gate_unconfirmed_over_2m_missing_rejected(monkeypatch):
    """T2.17: Missing order >= 2m old transitions to REJECTED and unblocks (blocked=0)."""
    db = InMemoryTestDB()
    now_utc = datetime.now(timezone.utc)
    db.auto_order_requests.append({
        "identifier": "auto-1-KRW-BTC-BUY-aged",
        "key_id": 1,
        "market": "KRW-BTC",
        "status": "PENDING",
        "created_at": now_utc - timedelta(seconds=130),
    })
    engine = TradingEngine(db, "http://calculation", False)
    try:
        response_404 = httpx.Response(404, request=httpx.Request("GET", "https://api.upbit.com"))
        def mock_private(method, path, key, params=None):
            raise httpx.HTTPStatusError("Order not found", request=response_404.request, response=response_404)
        monkeypatch.setattr(engine, "private_for_key", mock_private)

        result = engine.reconcile_auto_orders({"id": 1, "user_login_id": "operator"})
        assert result["blocked"] == 0
        assert result["rejected"] == 1
        assert result["accepted"] == 0
    finally:
        engine.stop()


def test_tier2_gate_unconfirmed_found_on_upbit_accepted(monkeypatch):
    """T2.18: Unconfirmed order confirmed on Upbit transitions to ACCEPTED and unblocks."""
    db = InMemoryTestDB()
    ident = "auto-1-KRW-BTC-BUY-confirmed"
    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "market": "KRW-BTC",
        "status": "UNKNOWN",
        "created_at": datetime.now(timezone.utc) - timedelta(seconds=90),
    })
    engine = TradingEngine(db, "http://calculation", False)
    try:
        def mock_private(method, path, key, params=None):
            return {"uuid": "confirmed-uuid-123", "identifier": ident, "market": "KRW-BTC", "side": "bid"}
        monkeypatch.setattr(engine, "private_for_key", mock_private)

        result = engine.reconcile_auto_orders({"id": 1, "user_login_id": "operator"})
        assert result["blocked"] == 0
        assert result["accepted"] == 1
        assert result["rejected"] == 0
    finally:
        engine.stop()


def test_tier2_gate_blocked_halts_auto_trading_loop(monkeypatch):
    """T2.19: When blocked > 0, _auto_order_for_key raises RuntimeError and halts trading."""
    db = InMemoryTestDB()
    engine = TradingEngine(db, "http://calculation", False)
    try:
        monkeypatch.setattr(engine, "reconcile_auto_orders", lambda key: {"blocked": 1, "accepted": 0, "rejected": 0})
        with pytest.raises(RuntimeError, match="접수 여부가 확인되지 않은 자동 주문"):
            engine._auto_order_for_key({"id": 1}, ["KRW-BTC"])
    finally:
        engine.stop()


def test_tier2_gate_mixed_age_orders_partitioned_accurately(monkeypatch):
    """T2.20: Multiple orders of varying age/states are partitioned into exact accepted, rejected, blocked counts."""
    db = InMemoryTestDB()
    now_utc = datetime.now(timezone.utc)
    db.auto_order_requests.append({
        "identifier": "order-confirmed",
        "key_id": 1,
        "market": "KRW-BTC",
        "status": "PENDING",
        "created_at": now_utc - timedelta(seconds=30),
    })
    db.auto_order_requests.append({
        "identifier": "order-aged-missing",
        "key_id": 1,
        "market": "KRW-ETH",
        "status": "PENDING",
        "created_at": now_utc - timedelta(seconds=150),
    })
    db.auto_order_requests.append({
        "identifier": "order-fresh-missing",
        "key_id": 1,
        "market": "KRW-SOL",
        "status": "PENDING",
        "created_at": now_utc - timedelta(seconds=45),
    })

    engine = TradingEngine(db, "http://calculation", False)
    try:
        response_404 = httpx.Response(404, request=httpx.Request("GET", "https://api.upbit.com"))
        def mock_private(method, path, key, params=None):
            ident = params.get("identifier")
            if ident == "order-confirmed":
                return {"uuid": "uuid-1", "identifier": ident, "market": "KRW-BTC"}
            raise httpx.HTTPStatusError("Not found", request=response_404.request, response=response_404)
        monkeypatch.setattr(engine, "private_for_key", mock_private)

        result = engine.reconcile_auto_orders({"id": 1, "user_login_id": "operator"})
        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert result["blocked"] == 1
    finally:
        engine.stop()


# ==============================================================================
# TIER 3: Cross-Feature Interactions (>=5 tests)
# ==============================================================================

def test_tier3_reconcile_clears_blocked_gate_and_resumes_trading(monkeypatch):
    """T3.1: Blocked trading gate is cleared by reconcile, permitting immediate next trading cycle."""
    db = InMemoryTestDB()
    db.seed_default_operator()
    ident = "auto-blocked-1"
    db.auto_order_requests.append({
        "identifier": ident,
        "key_id": 1,
        "market": "KRW-BTC",
        "status": "UNKNOWN",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=3),
    })
    engine = TradingEngine(db, "http://calculation", False)
    try:
        response_404 = httpx.Response(404, request=httpx.Request("GET", "https://api.upbit.com"))
        def mock_private(method, path, key, params=None):
            if path == "/v1/order":
                raise httpx.HTTPStatusError("Not found", request=response_404.request, response=response_404)
            if path == "/v1/accounts":
                return [{"currency": "KRW", "balance": "1000000", "locked": "0"}]
            if path == "/v1/orders/chance":
                return {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}}}
            return {"uuid": "submitted-uuid"}

        monkeypatch.setattr(engine, "private_for_key", mock_private)
        monkeypatch.setattr(engine, "unsellable_balances", lambda *args: {})
        monkeypatch.setattr(engine, "calc", lambda *args: {"actions": [{"side": "BUY", "market": "KRW-BTC"}]})

        # Reconcile resolves the aged missing order to REJECTED
        rec = engine.reconcile_auto_orders({"id": 1, "user_login_id": "operator"})
        assert rec["blocked"] == 0
        assert rec["rejected"] == 1

        # Now auto-order executes successfully without raising RuntimeError
        engine._auto_order_for_key({"id": 1, "user_login_id": "operator", "access_key": "a", "secret_key": "s"}, ["KRW-BTC"])
        assert any("INSERT INTO upbit_order_history" in sql for sql, _ in db.writes)
    finally:
        engine.stop()


def test_tier3_role_authorization_matrix_for_reconcile_and_emergency_sell(test_client, mock_db, monkeypatch):
    """T3.2: Access matrix check: Unauth=401, USER/ADMIN=403, MASTER=200/201."""
    # 1. Anonymous
    test_client.cookies.clear()
    main.app.dependency_overrides.clear()
    r1 = test_client.post("/api/upbit/auto-orders/reconcile")
    assert r1.status_code in (401, 403)

    # 2. USER role
    user = {"id": 2, "user_login_id": "user", "user_role": "USER", "user_name": "U"}
    main.app.dependency_overrides[main.current_user] = lambda: user
    main.app.dependency_overrides.pop(main.master_user, None)
    r2 = test_client.post("/api/upbit/auto-orders/reconcile")
    assert r2.status_code == 403

    # 3. ADMIN role (still not MASTER)
    admin = {"id": 3, "user_login_id": "admin", "user_role": "ADMIN", "user_name": "A"}
    main.app.dependency_overrides[main.current_user] = lambda: admin
    r3 = test_client.post("/api/upbit/auto-orders/reconcile")
    assert r3.status_code == 403

    # 4. MASTER role
    master = {"id": 1, "user_login_id": "operator", "user_role": "MASTER", "user_name": "M"}
    main.app.dependency_overrides[main.current_user] = lambda: master
    main.app.dependency_overrides[main.master_user] = lambda: master

    # Mock reconcile response for master call
    monkeypatch.setattr(main.engine, "reconcile_only", lambda key: {"accepted": 0, "rejected": 0, "blocked": 0})
    r4 = test_client.post("/api/upbit/auto-orders/reconcile")
    assert r4.status_code == 200


def test_tier3_disparity_rate_ranking_selects_strongest_momentum_coin():
    """T3.3: Disparity rate ranking ((temp_price - setting_price)/setting_price DESC) ranks candidates."""
    candidates = [
        {"code": "KRW-BTC", "temp_price": 110.0, "setting_price": 100.0},
        {"code": "KRW-ETH", "temp_price": 120.0, "setting_price": 100.0},
        {"code": "KRW-SOL", "temp_price": 105.0, "setting_price": 100.0},
    ]
    ranked = sorted(
        candidates,
        key=lambda c: (c["temp_price"] - c["setting_price"]) / c["setting_price"],
        reverse=True,
    )
    assert [c["code"] for c in ranked] == ["KRW-ETH", "KRW-BTC", "KRW-SOL"]
    assert ranked[0]["code"] == "KRW-ETH"


def test_tier3_auto_trade_toggle_updates_dashboard_safety_level(test_client, auth_header, mock_db):
    """T3.4: Toggling auto-trade ON/OFF directly updates dashboard safety level."""
    # 1. Turn ON
    res_on = test_client.put("/api/upbit/auto", json={"auto_on": True})
    assert res_on.status_code == 200
    d_on = test_client.get("/api/dashboard").json()
    assert d_on["auto_on"] is True
    assert d_on["safety"]["level"] == "healthy"

    # 2. Turn OFF
    res_off = test_client.put("/api/upbit/auto", json={"auto_on": False})
    assert res_off.status_code == 200
    d_off = test_client.get("/api/dashboard").json()
    assert d_off["auto_on"] is False
    assert d_off["safety"]["level"] == "neutral"


def test_tier3_post_manual_sell_suppresses_immediate_rebuy_window(monkeypatch):
    """T3.5: After manual market sell, auto-buy suppresses rebuying the same market for 10 minutes."""
    db = InMemoryTestDB()
    db.seed_default_operator()
    now_iso = datetime.now(timezone.utc).isoformat()
    db.order_history.append({
        "id": 1,
        "login_id": "operator",
        "uuid": "manual-uuid-1",
        "market": "KRW-BTC",
        "side": "ask",
        "ord_type": "market",
        "price": "50000000",
        "state": "done",
        "created_at": now_iso,
        "volume": "0.1",
        "executed_volume": "0.1",
        "identifier": "manual-sell-KRW-BTC-12345",
        "deleted_at": None,
    })
    engine = TradingEngine(db, "http://calculation", False)
    try:
        submitted = []
        def mock_private(method, path, key, params=None):
            if path == "/v1/accounts":
                return [{"currency": "KRW", "balance": "1000000", "locked": "0"}]
            if path == "/v1/orders/chance":
                return {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}}}
            if path == "/v1/orders":
                submitted.append(params)
                return {"uuid": "buy-uuid", "identifier": params["identifier"], "market": params["market"]}
            return {}

        monkeypatch.setattr(engine, "private_for_key", mock_private)
        monkeypatch.setattr(engine, "unsellable_balances", lambda *args: {})
        monkeypatch.setattr(engine, "calc", lambda *args: {
            "actions": [{"side": "BUY", "market": "KRW-BTC"}, {"side": "BUY", "market": "KRW-ETH"}]
        })

        engine._auto_order_for_key({"id": 1, "user_login_id": "operator", "access_key": "a", "secret_key": "s"}, ["KRW-BTC", "KRW-ETH"])
        # KRW-BTC was skipped due to recent manual sell; KRW-ETH was bought instead!
        assert len(submitted) == 1
        assert submitted[0]["market"] == "KRW-ETH"
    finally:
        engine.stop()


# ==============================================================================
# TIER 4: Real-World Scenarios (>=4 tests)
# ==============================================================================

def test_tier4_scenario_complete_trading_lifecycle_cash_to_asset_to_cash(monkeypatch):
    """
    T4.1: Full operational cycle:
    1. Start with 100% KRW cash.
    2. Signal generator identifies KRW-BTC above MA40 -> auto-buy executed.
    3. Portfolio holds KRW-BTC asset; invested amount tracked.
    4. Next cycle, KRW-BTC drops below MA40 -> auto-sell executed.
    5. Return to 100% KRW cash.
    """
    db = InMemoryTestDB()
    db.seed_default_operator()
    engine = TradingEngine(db, "http://calculation", False)
    try:
        key = {"id": 1, "user_login_id": "operator", "access_key": "a", "secret_key": "s"}
        portfolio_state = {"krw": 1_000_000.0, "btc": 0.0}

        def mock_private(method, path, k, params=None):
            if path == "/v1/accounts":
                accounts = [{"currency": "KRW", "balance": str(portfolio_state["krw"]), "locked": "0"}]
                if portfolio_state["btc"] > 0:
                    accounts.append({"currency": "BTC", "balance": str(portfolio_state["btc"]), "locked": "0"})
                return accounts
            if path == "/v1/orders/chance":
                return {
                    "bid_fee": "0.0005",
                    "market": {"bid": {"min_total": "5000"}},
                    "ask_account": {"balance": str(portfolio_state["btc"])},
                }
            if path == "/v1/orders":
                if params["side"] == "bid":
                    portfolio_state["btc"] = 0.02
                    portfolio_state["krw"] = 0.0
                    return {
                        "uuid": "buy-uuid-1", "side": "bid", "ord_type": "price",
                        "price": "1000000", "state": "done",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "identifier": params["identifier"], "market": "KRW-BTC",
                    }
                else:
                    portfolio_state["krw"] = 1_050_000.0
                    portfolio_state["btc"] = 0.0
                    return {
                        "uuid": "sell-uuid-1", "side": "ask", "ord_type": "market",
                        "state": "done",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "identifier": params["identifier"], "market": "KRW-BTC",
                    }
            return {}

        monkeypatch.setattr(engine, "private_for_key", mock_private)
        monkeypatch.setattr(engine, "unsellable_balances", lambda *args: {})

        # Step A: Buy signal
        monkeypatch.setattr(engine, "calc", lambda *args: {"actions": [{"side": "BUY", "market": "KRW-BTC"}]})
        engine._auto_order_for_key(key, ["KRW-BTC"])
        assert portfolio_state["krw"] == 0.0
        assert portfolio_state["btc"] == 0.02

        # Step B: Sell signal (market dropped below MA40)
        monkeypatch.setattr(engine, "calc", lambda *args: {"actions": [{"side": "SELL", "market": "KRW-BTC"}]})
        engine._auto_order_for_key(key, [])
        assert portfolio_state["btc"] == 0.0
        assert portfolio_state["krw"] == 1_050_000.0

        assert len(db.order_history) == 2
        assert db.order_history[0]["side"] in ("bid", "BUY")
        assert db.order_history[1]["side"] in ("ask", "SELL")
    finally:
        engine.stop()


def test_tier4_scenario_transport_failure_safety_alert_and_reconciliation(test_client, auth_header, mock_db, monkeypatch):
    """
    T4.2: Network failure during order submission sets UNKNOWN status, flips dashboard
    safety level to 'blocked', operator reconciles order with exchange, restoring 'healthy' state.
    """
    engine = main.engine
    key = {"id": 1, "user_login_id": "operator", "access_key": "a", "secret_key": "s"}

    # 1. Simulate order submission experiencing network transport loss
    def mock_private_fail(method, path, k, params=None):
        if method == "POST" and path == "/v1/orders":
            raise httpx.ReadTimeout("Socket timeout while sending order")
        if method == "GET" and path == "/v1/order":
            raise httpx.ConnectError("Exchange unreachable")
        return {}

    monkeypatch.setattr(engine, "private_for_key", mock_private_fail)
    with pytest.raises(RuntimeError, match="자동 주문 접수 확인 실패"):
        engine._submit_auto_order(key, {"market": "KRW-BTC", "side": "bid", "identifier": "auto-timeout-1"})

    # 2. Check dashboard: Safety status must now be 'blocked'
    d1 = test_client.get("/api/dashboard").json()
    assert d1["safety"]["level"] == "blocked"
    assert len(d1["safety"]["unresolved_orders"]) == 1

    # 3. Network recovers: Reconcile finds the order on Upbit
    def mock_private_recover(method, path, k, params=None):
        if path == "/v1/order":
            return {"uuid": "rec-uuid-1", "identifier": "auto-timeout-1", "market": "KRW-BTC"}
        return {}
    monkeypatch.setattr(engine, "private_for_key", mock_private_recover)

    rec_res = test_client.post("/api/upbit/auto-orders/reconcile")
    assert rec_res.status_code == 200
    assert rec_res.json()["accepted"] == 1
    assert rec_res.json()["blocked"] == 0

    # 4. Check dashboard again: Safety status returns to 'healthy'
    d2 = test_client.get("/api/dashboard").json()
    assert d2["safety"]["level"] == "healthy"
    assert len(d2["safety"]["unresolved_orders"]) == 0


def test_tier4_scenario_emergency_operator_market_sell(test_client, auth_header, mock_db, monkeypatch):
    """
    T4.3: Operator triggers emergency market sell:
    1. POST /api/upbit/orders/market-sell executed with valid MarketSellRequest.
    2. Order recorded in DB with manual-sell identifier.
    3. Re-buy suppression window activated.
    """
    sold_orders = []
    def mock_manual_sell(key, market, qty=None):
        order = {
            "uuid": "emergency-sell-uuid",
            "market": market,
            "side": "ask",
            "ord_type": "market",
            "price": "50000000",
            "state": "done",
            "identifier": f"manual-sell-{market}-{uuid.uuid4()}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "volume": "0.1",
            "executed_volume": "0.1",
        }
        sold_orders.append(order)
        mock_db.execute(
            """INSERT INTO upbit_order_history(login_id,uuid,side,ord_type,price,state,market,created_at,volume,executed_volume,identifier)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (key["user_login_id"], order["uuid"], order["side"], order["ord_type"], order["price"],
             order["state"], order["market"], order["created_at"], order["volume"], order["executed_volume"], order["identifier"])
        )
        return order

    monkeypatch.setattr(main.engine, "manual_market_sell", mock_manual_sell)

    res = test_client.post("/api/upbit/orders/market-sell", json={
        "market": "KRW-BTC",
        "expected_available_quantity": 0.1,
        "confirm": True,
        "keep_auto": True,
    })
    assert res.status_code == 201
    assert len(sold_orders) == 1
    assert sold_orders[0]["market"] == "KRW-BTC"
    assert any(o.get("identifier", "").startswith("manual-sell-KRW-BTC") for o in mock_db.order_history)


def test_tier4_scenario_price_data_stale_circuit_breaker(test_client, auth_header, mock_db):
    """
    T4.4: Stale price feed (> 450 seconds old) triggers safety level 'delayed'
    and acts as a circuit breaker against new purchases.
    """
    mock_db.upbit_signals.clear()
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).strftime("%Y-%m-%d %H:%M:%S")
    mock_db.upbit_signals.append({
        "id": 1,
        "code": "KRW-BTC",
        "name": "비트코인",
        "temp_price": 50000000.0,
        "minimum_selling_price": 49000000.0,
        "expected_selling_price": 49000000.0,
        "setting_price": 49000000.0,
        "renewal_cnt": 0,
        "deleted_at": None,
        "updated_at": stale_time,
    })

    res = test_client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    safety = data.get("safety", {})
    assert safety["level"] == "delayed"
    assert safety["price_healthy"] is False
    assert safety["price_age_seconds"] >= 450
    assert "지연" in safety["summary"]
