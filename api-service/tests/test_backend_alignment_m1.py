import pytest
from starlette.testclient import TestClient
from app import main
from app.trading import TradingEngine


def test_ma40_api_paths_contains_profile_and_market_sell():
    assert "/api/profile" in main._MA40_API_PATHS
    assert "/api/upbit/orders/market-sell" in main._MA40_API_PATHS
    assert "/api/upbit/auto-orders/reconcile" in main._MA40_API_PATHS
    assert "/api/upbit/auto-markets" in main._MA40_API_PATHS
    assert "/api/upbit/recollect" in main._MA40_API_PATHS
    assert "/api/backtest/batch" in main._MA40_API_PATHS
    assert "/api/upbit/recommendation-prefs" in main._MA40_API_PATHS


def test_upbit_candle_path_supports_30m_60m_240m_days_weeks():
    assert TradingEngine.upbit_candle_path("30m") == "/v1/candles/minutes/30"
    assert TradingEngine.upbit_candle_path("60m") == "/v1/candles/minutes/60"
    assert TradingEngine.upbit_candle_path("240m") == "/v1/candles/minutes/240"
    assert TradingEngine.upbit_candle_path("days") == "/v1/candles/days"
    assert TradingEngine.upbit_candle_path("weeks") == "/v1/candles/weeks"


def test_auto_order_only_buys_enabled_markets_but_sells_any_held_below_ma(monkeypatch):
    submitted = []

    class MockDb:
        def all(self, query, params=()):
            if "SELECT code FROM upbit" in query:
                return [{"code": "KRW-BTC"}, {"code": "KRW-ETH"}]
            if "WHERE auto_trade=true" in query:
                return [{"market": "KRW-ETH"}]
            if "SELECT k.* FROM tb_upbit_key" in query:
                return [{"id": 1, "user_login_id": "op", "access_key": "ak", "secret_key": "sk"}]
            return []

        def one(self, query, params=()):
            return {"id": 1}

    engine = TradingEngine(MockDb(), "http://calc", False)
    monkeypatch.setattr(engine, "reconcile_auto_orders", lambda *_: {"blocked": 0})
    monkeypatch.setattr(engine, "unsellable_balances", lambda *_: {})
    monkeypatch.setattr(engine, "private_for_key", lambda method, path, key, params=None: (
        [{"currency": "KRW", "balance": "100000", "locked": "0"}]
        if path == "/v1/accounts"
        else {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}}}
    ))
    monkeypatch.setattr(engine, "calc", lambda path, payload: {
        "actions": [{"side": "BUY", "market": m} for m in payload["recommended_markets"]]
    })
    monkeypatch.setattr(engine, "_submit_auto_order", lambda key, params: submitted.append(params) or {"uuid": "u-1"})
    monkeypatch.setattr(engine, "save_order", lambda *_: None)

    engine._auto_order()
    assert len(submitted) == 1
    assert submitted[0]["market"] == "KRW-ETH"
    assert submitted[0]["side"] == "bid"


def test_first_user_registration_is_granted_master_role(monkeypatch):
    calls = []
    class MockDb:
        def one(self, query, params=()):
            return None  # No existing user, not taken
        def execute(self, query, params=()):
            calls.append((query, params))
            return 1

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main, "SIGNUP_ENABLED", True)

    payload = main.JoinRequest(login_id="firstoperator", password="password123", name="Operator", email="op@example.com", phone="010-1234-5678")
    result = main.join(payload)
    assert result == {"ok": True}
    assert len(calls) == 1
    query, params = calls[0]
    assert "'MASTER'" in query
    assert params[0] == "firstoperator"


def test_subsequent_user_registration_is_granted_user_role(monkeypatch):
    calls = []
    existing_ids = {"master"}

    class MockDb:
        def one(self, query, params=()):
            if "WHERE user_login_id=%s" in query:
                return {"id": 1} if params[0] in existing_ids else None
            if "WHERE deleted_at IS NULL LIMIT 1" in query:
                return {"id": 1}
            return None

        def execute(self, query, params=()):
            calls.append((query, params))
            existing_ids.add(params[0])
            return 1

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main, "SIGNUP_ENABLED", True)

    payload = main.JoinRequest(login_id="seconduser", password="password123", name="일반사용자")
    result = main.join(payload)
    assert result == {"ok": True}
    assert len(calls) == 1
    query, params = calls[0]
    assert "'USER'" in query
    assert params[0] == "seconduser"

    client = TestClient(main.app)
    dup_res = client.post("/api/auth/join", json={"login_id": "seconduser", "password": "password123", "name": "중복"})
    assert dup_res.status_code == 409


def test_disparity_rate_ranking_in_recommendations(monkeypatch):
    main.app.dependency_overrides[main.current_user] = lambda: {"id": 1, "user_login_id": "master", "user_role": "MASTER"}
    executed_queries = []

    class MockDb:
        def one(self, query, params=()):
            return None
        def all(self, query, params=()):
            executed_queries.append(query)
            return []
        def execute(self, query, params=()):
            return 0

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main.engine, "account_snapshot", lambda *args: {"total_valuation": 0, "assets": []})

    client = TestClient(main.app)
    response = client.get("/api/dashboard")
    assert response.status_code == 200

    rec_query = next((q for q in executed_queries if "FROM upbit u" in q), None)
    assert rec_query is not None
    assert "ORDER BY ((u.temp_price - u.setting_price) / NULLIF(u.setting_price, 0)) DESC NULLS LAST, u.id DESC" in rec_query


def test_disparity_rate_ranking_in_auto_order():
    queries = []
    class MockDb:
        def all(self, query, params=()):
            queries.append(query)
            return []

    engine = TradingEngine(MockDb(), "http://calc", False)
    # Call _auto_order directly to verify the markets ordering SQL
    result = engine._auto_order()
    market_query = next((q for q in queries if "SELECT code FROM upbit" in q), None)
    assert market_query is not None
    assert "ORDER BY ((temp_price - setting_price) / NULLIF(setting_price, 0)) DESC NULLS LAST" in market_query
    assert "id DESC" in market_query


def test_no_us_rate_limited_name_error_on_exception(monkeypatch):
    class MockDb:
        def all(self, query, params=()):
            return [{"code": "KRW-BTC", "name": "Bitcoin", "expected_selling_price": 100, "minimum_selling_price": 90, "temp_price": 95, "setting_price": 90, "renewal_cnt": 0}]

    engine = TradingEngine(MockDb(), "http://calc", False)
    monkeypatch.setattr(engine, "setting", lambda *_: {"expected_high_percentage": 10, "expected_low_percentage": -5})
    monkeypatch.setattr(engine, "record_error", lambda *args: None)

    def failing_loader(code, count):
        raise RuntimeError("Transient network issue")

    # This should not raise NameError: name 'USRateLimited' is not defined
    engine._update_positions("upbit", failing_loader)


def test_dashboard_surfaces_inactive_auto_trade_markets_that_dropped_from_recommendations(monkeypatch):
    main.app.dependency_overrides[main.current_user] = lambda: {"id": 1, "user_login_id": "master", "user_role": "MASTER"}

    class MockDb:
        def one(self, query, params=()):
            return None

        def all(self, query, params=()):
            if "WHERE auto_trade=true" in query:
                return [{"market": "KRW-BTC"}, {"market": "KRW-XRP"}]
            if "FROM upbit u" in query:
                return [{
                    "code": "KRW-BTC",
                    "name": "비트코인",
                    "temp_price": 100000000.0,
                    "minimum_selling_price": 95000000.0,
                    "expected_selling_price": 105000000.0,
                    "setting_price": 95000000.0,
                    "renewal_cnt": 1,
                    "updated_at": "2026-11-10 08:00:00",
                    "ma_period": 40,
                    "auto_trade": True,
                }]
            if "FROM unnest" in query:
                return [{
                    "code": "KRW-XRP",
                    "name": "리플",
                    "temp_price": 800.0,
                    "setting_price": 850.0,
                    "updated_at": "2026-11-10 07:55:00",
                    "deleted_at": "2026-11-10 07:55:00",
                }]
            return []

        def execute(self, query, params=()):
            return 0

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main.engine, "account_snapshot", lambda *args: {"total_valuation": 0, "assets": []})

    client = TestClient(main.app)
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    body = res.json()
    assert body["auto_trade_markets"] == ["KRW-BTC", "KRW-XRP"]
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["code"] == "KRW-BTC"
    assert body["recommendations"][0]["auto_trade_rank"] == 1
    assert len(body["inactive_auto_trade_items"]) == 1
    assert body["inactive_auto_trade_items"][0]["code"] == "KRW-XRP"
    assert body["inactive_auto_trade_items"][0]["name"] == "리플"
    assert body["inactive_auto_trade_items"][0]["status"] == "SIGNAL_DROPPED"


def test_manual_market_sell_disables_auto_trade_for_sold_market(monkeypatch):
    user = {"id": 1, "user_login_id": "master", "user_role": "MASTER"}
    main.app.dependency_overrides[main.current_user] = lambda: user
    main.app.dependency_overrides[main.master_user] = lambda: user
    executed = []

    class MockDb:
        def one(self, query, params=()):
            return {"id": 1, "user_login_id": "master", "access_key": "a", "secret_key": "s"}

        def execute(self, query, params=()):
            executed.append((query, params))
            return 1

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main.engine, "manual_market_sell", lambda key, market, qty: {"ok": True, "uuid": "sell-1", "market": market})

    client = TestClient(main.app)
    res = client.post("/api/upbit/orders/market-sell", json={
        "market": "KRW-BTC",
        "expected_available_quantity": "0.1",
        "confirm": True,
        "keep_auto": True,
    })
    assert res.status_code == 201
    assert res.json()["auto_trade_disabled"] is True
    assert any("UPDATE upbit_strategy_settings SET auto_trade=false" in q and p == ("KRW-BTC",) for q, p in executed)


def test_evaluate_ma_backtest_computes_metrics_from_upbit_order_prices():
    # Chronological: 5 bars at 100, then bar 5 at 110 (signal), bar 6 BUY at 110 & close 150, bar 7 close 80, bar 8 SELL at 140
    chronological = [
        {"open": 100, "close": 100},
        {"open": 100, "close": 100},
        {"open": 100, "close": 100},
        {"open": 100, "close": 100},
        {"open": 100, "close": 100},
        {"open": 110, "close": 110},
        {"open": 110, "close": 150},
        {"open": 150, "close": 80},
        {"open": 140, "close": 80},
    ]
    # Upbit order is newest first
    upbit_order = list(reversed(chronological))
    bt = TradingEngine.evaluate_ma_backtest(upbit_order, ma_period=5, initial_capital=1_000_000, fee_bps=5, slippage_bps=10)
    assert bt["bt_trade_count"] == 1
    assert bt["bt_win_rate_pct"] == 100.0
    assert bt["bt_return_pct"] > 20.0
    assert "bt_benchmark_pct" in bt
    assert "bt_excess_pct" in bt
    assert "bt_mdd_pct" in bt


def test_update_recommendation_prefs_endpoint(monkeypatch):
    user = {"id": 1, "user_login_id": "master", "user_role": "MASTER"}
    main.app.dependency_overrides[main.current_user] = lambda: user
    executed = []

    class MockDb:
        def all(self, query, params=()):
            return []

        def execute(self, query, params=()):
            executed.append((query, params))
            return 1

    monkeypatch.setattr(main, "db", MockDb())
    client = TestClient(main.app)
    res = client.put(
        "/api/upbit/recommendation-prefs",
        json={"sort_by": "bt_return_desc", "exclude_negative_bt": True},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "sort_by": "bt_return_desc", "exclude_negative_bt": True}
    assert any("INSERT INTO upbit_strategy_settings" in q for q, _ in executed)


def test_batch_backtest_endpoint_updates_active_recommendations(monkeypatch):
    user = {"id": 1, "user_login_id": "master", "user_role": "MASTER"}
    main.app.dependency_overrides[main.current_user] = lambda: user
    executed = []

    class MockDb:
        def all(self, query, params=()):
            if "FROM upbit_strategy_settings" in query:
                return [{"market": "__GLOBAL__", "candle_interval": "days", "ma_period": 5, "days": 60}]
            if "FROM upbit WHERE deleted_at IS NULL" in query:
                return [
                    {"code": "KRW-BTC", "bt_return_pct": None, "bt_candle_interval": None, "bt_ma_period": None},
                    {"code": "KRW-ETH", "bt_return_pct": 12.5, "bt_candle_interval": "days", "bt_ma_period": 5},
                ]
            return []

        def execute(self, query, params=()):
            executed.append((query, params))
            return 1

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(
        main.engine,
        "upbit_prices",
        lambda code, count, *args: [{"open": 100 + i, "close": 100 + i} for i in range(20)],
    )
    client = TestClient(main.app)
    res = client.post("/api/backtest/batch", json={"force": False})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["updated_count"] == 1
    assert "KRW-BTC" in body["items"]
    assert body["items"]["KRW-BTC"]["code"] == "KRW-BTC"
    assert any("UPDATE upbit" in q and p[-1] == "KRW-BTC" for q, p in executed)


def test_dashboard_sorts_by_bt_return_desc_and_excludes_negative_bt_from_rank(monkeypatch):
    user = {"id": 1, "user_login_id": "master", "user_role": "MASTER"}
    main.app.dependency_overrides[main.current_user] = lambda: user

    class MockDb:
        def one(self, query, params=()):
            return None

        def all(self, query, params=()):
            if "ORDER BY CASE WHEN market='__GLOBAL__'" in query:
                return [{
                    "market": "__GLOBAL__",
                    "candle_interval": "days",
                    "ma_period": 40,
                    "days": 180,
                    "initial_capital": 1000000.0,
                    "fee_bps": 5.0,
                    "slippage_bps": 10.0,
                    "sort_by": "bt_return_desc",
                    "exclude_negative_bt": True,
                }]
            if "WHERE auto_trade=true" in query:
                return [{"market": "KRW-BTC"}, {"market": "KRW-ETH"}, {"market": "KRW-SOL"}]
            if "FROM upbit u" in query:
                return [
                    {
                        "id": 3,
                        "code": "KRW-BTC",
                        "name": "비트코인",
                        "temp_price": 110.0,
                        "minimum_selling_price": 95.0,
                        "expected_selling_price": 120.0,
                        "setting_price": 100.0,
                        "renewal_cnt": 1,
                        "updated_at": "2026-11-10 08:00:00",
                        "bt_return_pct": -5.2,
                        "bt_excess_pct": -2.0,
                        "bt_mdd_pct": 12.0,
                        "bt_trade_count": 3,
                        "bt_win_rate_pct": 33.33,
                        "ma_period": 40,
                        "auto_trade": True,
                    },
                    {
                        "id": 2,
                        "code": "KRW-ETH",
                        "name": "이더리움",
                        "temp_price": 105.0,
                        "minimum_selling_price": 95.0,
                        "expected_selling_price": 120.0,
                        "setting_price": 100.0,
                        "renewal_cnt": 1,
                        "updated_at": "2026-11-10 08:00:00",
                        "bt_return_pct": 24.5,
                        "bt_excess_pct": 10.0,
                        "bt_mdd_pct": 8.0,
                        "bt_trade_count": 4,
                        "bt_win_rate_pct": 75.0,
                        "ma_period": 40,
                        "auto_trade": True,
                    },
                    {
                        "id": 1,
                        "code": "KRW-SOL",
                        "name": "솔라나",
                        "temp_price": 102.0,
                        "minimum_selling_price": 95.0,
                        "expected_selling_price": 120.0,
                        "setting_price": 100.0,
                        "renewal_cnt": 1,
                        "updated_at": "2026-11-10 08:00:00",
                        "bt_return_pct": 8.1,
                        "bt_excess_pct": 3.0,
                        "bt_mdd_pct": 6.0,
                        "bt_trade_count": 2,
                        "bt_win_rate_pct": 50.0,
                        "ma_period": 40,
                        "auto_trade": True,
                    },
                ]
            return []

        def execute(self, query, params=()):
            return 0

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main.engine, "account_snapshot", lambda *args: {"total_valuation": 0, "assets": []})

    client = TestClient(main.app)
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    body = res.json()
    recs = body["recommendations"]
    assert [r["code"] for r in recs] == ["KRW-ETH", "KRW-SOL", "KRW-BTC"]
    assert recs[0]["auto_trade_rank"] == 1
    assert recs[0]["auto_trade_excluded_reason"] is None
    assert recs[1]["auto_trade_rank"] == 2
    assert recs[1]["auto_trade_excluded_reason"] is None
    assert recs[2]["auto_trade_rank"] is None
    assert recs[2]["auto_trade_excluded_reason"] == "negative_bt"


def test_dashboard_syncs_pending_wait_orders_before_returning_recent_orders(monkeypatch):
    main.app.dependency_overrides[main.current_user] = lambda: {"id": 1, "user_login_id": "stxtory", "user_role": "MASTER"}
    orders = [
        {
            "uuid": "wait-sell-1",
            "side": "ask",
            "ord_type": "market",
            "price": None,
            "state": "wait",
            "market": "KRW-PIEVERSE",
            "created_at": "2026-11-12T08:27:00+09:00",
            "volume": "19.64106908",
            "executed_volume": "0",
        },
        {
            "uuid": "done-old-1",
            "side": "ask",
            "ord_type": "market",
            "price": None,
            "state": "done",
            "market": "KRW-IMX",
            "created_at": "2026-10-11T03:00:22+09:00",
            "volume": "255.27",
            "executed_volume": "255.27",
        },
    ]

    class MockDb:
        def one(self, query, params=()):
            if "tb_upbit_key" in query:
                return {"id": 1, "user_login_id": "stxtory", "access_key": "ak", "secret_key": "sk", "auto_on": False}
            return None

        def all(self, query, params=()):
            if "SELECT uuid, state FROM upbit_order_history" in query:
                return [o for o in orders if o["state"] not in ("done", "cancel")]
            if "FROM upbit_order_history" in query and "LIMIT 5" in query:
                return list(orders)
            return []

        def execute(self, query, params=()):
            if "UPDATE upbit_order_history SET state=" in query:
                state, price, volume, _rem, executed_vol, _fee, _cnt, _upd, _login, target_uuid = params
                for o in orders:
                    if o["uuid"] == target_uuid:
                        o.update(state=state, price=price, volume=volume, executed_volume=executed_vol)
                return 1
            return 0

    upbit_queries = []

    def mock_private(method, path, access, secret, params=None):
        upbit_queries.append((method, path, params))
        return [{
            "uuid": "wait-sell-1",
            "state": "done",
            "price": None,
            "volume": "19.64106908",
            "remaining_volume": "0",
            "executed_volume": "19.64106908",
            "paid_fee": "21.6",
            "trades_count": 1,
        }]

    monkeypatch.setattr(main, "db", MockDb())
    monkeypatch.setattr(main.engine, "key_credentials", lambda key, login_id: ("ak", "sk"))
    monkeypatch.setattr(main.engine, "account_snapshot", lambda *args: {"total_valuation": 43188.76, "assets": []})
    monkeypatch.setattr(main.engine, "private_upbit", mock_private)

    try:
        client = TestClient(main.app)
        res = client.get("/api/dashboard")
        assert res.status_code == 200
        recent = res.json()["recent_orders"]
        assert recent[0]["uuid"] == "wait-sell-1"
        assert recent[0]["state"] == "done"
        assert recent[0]["executed_volume"] == "19.64106908"
        assert upbit_queries == [("GET", "/v1/orders/uuids", {"uuids[]": ["wait-sell-1"]})]

        # Second dashboard poll: all orders terminal -> zero extra Upbit /v1/orders/uuids calls
        res2 = client.get("/api/dashboard")
        assert res2.status_code == 200
        assert len(upbit_queries) == 1
    finally:
        main.app.dependency_overrides.clear()



