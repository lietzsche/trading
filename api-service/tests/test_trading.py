import hashlib
import threading
from urllib.parse import urlencode

import httpx
import jwt
import pytest

from app.trading import TradingEngine


class NoopDatabase:
    def execute(self, *_):
        pass


class TradingDatabase:
    def __init__(self):
        self.queries = []
        self.writes = []
        self.keys = [
            {"id": 1, "user_login_id": "first", "access_key": "first", "secret_key": "test-secret"},
            {"id": 2, "user_login_id": "second", "access_key": "second", "secret_key": "test-secret"},
        ]
        self.active = True

    def all(self, sql, params=()):
        self.queries.append((sql, params))
        return [{"code": "KRW-BTC"}] if "SELECT DISTINCT code" in sql else self.keys

    def one(self, sql, params=()):
        self.queries.append((sql, params))
        return {"id": params[0]} if self.active else None

    def execute(self, sql, params=()):
        self.writes.append((sql, params))


@pytest.fixture
def trading_engine():
    engine = TradingEngine(TradingDatabase(), "http://calculation", False)
    yield engine
    engine.stop()


def test_upbit_order_token_contains_matching_query_hash():
    params = {"market": "KRW-BTC", "side": "bid", "price": "5000", "ord_type": "price"}
    token = TradingEngine.token("access", "secret", params)
    claims = jwt.decode(token, "secret", algorithms=["HS256"])
    assert claims["access_key"] == "access"
    assert claims["query_hash"] == hashlib.sha512(urlencode(params).encode()).hexdigest()
    assert claims["query_hash_alg"] == "SHA512"


def test_upbit_token_hashes_array_parameters_without_url_encoding():
    params = {"uuids[]": ["first", "second"]}
    token = TradingEngine.token("access", "secret", params)
    claims = jwt.decode(token, "secret", algorithms=["HS256"])
    expected = "uuids[]=first&uuids[]=second"
    assert claims["query_hash"] == hashlib.sha512(expected.encode()).hexdigest()


def test_scheduler_is_off_until_explicitly_enabled():
    engine = TradingEngine(NoopDatabase(), "http://calculation", False)
    engine.start()
    assert engine.scheduler.running is False


def test_stock_parser_skips_invalid_rows(monkeypatch):
    body = """<table class='type2'><tr><td>2026.09.09</td><td>10,000</td><td>0</td>
    <td>9,000</td><td>11,000</td><td>8,000</td><td>123,456</td></tr></table>"""
    response = type("Response", (), {"text": body, "raise_for_status": lambda self: None})()
    monkeypatch.setattr("app.trading.httpx.get", lambda *args, **kwargs: response)
    assert TradingEngine.stock_prices("000000", 1)[0]["close"] == 10000


def test_stock_universe_uses_named_columns(monkeypatch):
    body = """<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th></tr>
    <tr><td>테스트</td><td>코스피</td><td>1234</td></tr></table>""".encode()
    response = type("Response", (), {"content": body, "raise_for_status": lambda self: None})()
    monkeypatch.setattr("app.trading.httpx.get", lambda *args, **kwargs: response)
    assert TradingEngine.stock_universe() == [{"name": "테스트", "code": "001234"}]


def test_dividend_parser_reads_code_name_and_rate():
    body = """<table class='type_1'><tr><td class='frst'><a
      href='/item/main.naver?code=005930'>삼성전자</a></td><td>70,000</td><td>25.12</td>
      <td>1,500</td><td>2.14</td></tr><tr><td>빈 행</td></tr></table>"""
    assert TradingEngine.parse_dividend_page(body) == [
        {"code": "005930", "name": "삼성전자", "dividend_rate": 2.14}
    ]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_auto_order_isolates_failed_accounts_and_only_disables_auth_failures(trading_engine, monkeypatch, status):
    calls = []

    def private(method, path, access, secret, params=None):
        calls.append((method, path, access))
        assert method == "GET" and path == "/v1/accounts"
        if access == "first":
            response = httpx.Response(status, request=httpx.Request("GET", "https://api.upbit.com/v1/accounts"))
            response.raise_for_status()
        return []

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": []})
    result = trading_engine.auto_order()
    assert result == {"status": "PARTIAL", "completed_accounts": 1, "failed_accounts": 1}
    assert [call[2] for call in calls] == ["first", "second"]
    disabled = [params for sql, params in trading_engine.db.writes if "SET auto_on=false" in sql]
    assert disabled == ([(1, "first", "test-secret")] if status in (401, 403) else [])
    errors = [params for sql, params in trading_engine.db.writes if "trade_error_log" in sql]
    assert len(errors) == 1
    assert errors[0][:3] == ("UPBIT", "AUTO_ORDER_ACCOUNT_1", "HTTPStatusError")
    key_query = next(sql for sql, _ in trading_engine.db.queries if "SELECT k.*" in sql)
    assert "JOIN tb_user" in key_query
    assert "k.auto_on=true" in key_query and "u.deleted_at IS NULL" in key_query


def test_auto_order_isolates_non_http_errors(trading_engine, monkeypatch):
    calls = []

    def process(key, markets):
        calls.append(key["id"])
        if key["id"] == 1:
            raise ValueError("Invalid calculation response")

    monkeypatch.setattr(trading_engine, "_auto_order_for_key", process)
    result = trading_engine.auto_order()
    assert calls == [1, 2]
    assert result["failed_accounts"] == 1


def test_auto_order_skips_overlapping_manual_and_scheduler_runs(trading_engine, monkeypatch):
    started, release = threading.Event(), threading.Event()
    results = []

    def process():
        started.set()
        assert release.wait(3)
        return {"status": "OK"}

    monkeypatch.setattr(trading_engine, "_auto_order", process)
    worker = threading.Thread(target=lambda: results.append(trading_engine.auto_order()))
    worker.start()
    try:
        assert started.wait(3)
        assert trading_engine.auto_order() == {"status": "SKIPPED", "reason": "already_running"}
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results == [{"status": "OK"}]
    assert not trading_engine._auto_order_lock.locked()


def test_auto_order_releases_lock_after_failure(trading_engine, monkeypatch):
    def fail():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(trading_engine, "_auto_order", fail)
    assert trading_engine.auto_order() == {"status": "ERROR"}
    assert not trading_engine._auto_order_lock.locked()
    monkeypatch.setattr(trading_engine, "_auto_order", lambda: {"status": "OK"})
    assert trading_engine.auto_order() == {"status": "OK"}


def test_job_run_preserves_successful_none_result(trading_engine):
    assert trading_engine.run("STOCK", "SCHEDULE_UPDATE", lambda: None) is None
    assert trading_engine.db.writes == []


def test_job_run_returns_failure_status_and_records_original_error(trading_engine):
    def fail():
        raise ValueError("Invalid upstream data")

    assert trading_engine.run("STOCK", "SCHEDULE_UPDATE", fail) == {"status": "ERROR"}
    sql, params = trading_engine.db.writes[0]
    assert "INSERT INTO trade_error_log" in sql
    assert params[:4] == ("STOCK", "SCHEDULE_UPDATE", "ValueError", "Invalid upstream data")


@pytest.mark.parametrize("active", [True, False])
def test_order_checks_current_permission_and_keeps_existing_buy_amount(trading_engine, monkeypatch, active):
    calls, saved = [], []
    trading_engine.db.active = active

    def private(method, path, access, secret, params=None):
        calls.append((method, path, params))
        if path == "/v1/accounts":
            return [{"currency": "KRW", "balance": "10000", "locked": "0"}]
        if path == "/v1/orders/chance":
            return {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}}}
        assert method == "POST" and path == "/v1/orders"
        return {"uuid": "mock-order"}

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": [{"market": "KRW-BTC", "side": "BUY"}]})
    monkeypatch.setattr(trading_engine, "save_order", lambda *args: saved.append(args))
    trading_engine._auto_order_for_key(trading_engine.db.keys[0], ["KRW-BTC"])
    orders = [params for method, _, params in calls if method == "POST"]
    assert len(orders) == int(active)
    assert len(saved) == int(active)
    permission_query, params = trading_engine.db.queries[-1]
    assert "k.auto_on=true" in permission_query and "u.deleted_at IS NULL" in permission_query
    assert "k.access_key=%s AND k.secret_key=%s" in permission_query
    assert params == (1, "first", "test-secret")
    if active:
        assert orders[0] == {"market": "KRW-BTC", "side": "bid", "price": "9995.0", "ord_type": "price"}


def test_sell_skips_zero_available_balance(trading_engine, monkeypatch):
    calls = []

    def private(method, path, access, secret, params=None):
        calls.append(method)
        assert method == "GET"
        if path == "/v1/accounts":
            return [{"currency": "BTC", "balance": "0", "locked": "1"}]
        return {"ask_account": {"balance": "0"}}

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": [{"market": "KRW-BTC", "side": "SELL"}]})
    trading_engine._auto_order_for_key(trading_engine.db.keys[0], [])
    assert calls == ["GET", "GET"]


def test_account_snapshot_preserves_unknown_prices_and_non_krw_costs(trading_engine, monkeypatch):
    accounts = [
        {"currency": "KRW", "balance": "5000", "locked": "1000", "avg_buy_price": "0", "unit_currency": "KRW"},
        {"currency": "BTC", "balance": "1", "locked": "1", "avg_buy_price": "10000", "unit_currency": "KRW"},
        {"currency": "OLD", "balance": "2", "locked": "0", "avg_buy_price": "50", "unit_currency": "KRW"},
        {"currency": "ETH", "balance": "3", "locked": "0", "avg_buy_price": "0.01", "unit_currency": "BTC"},
        {"currency": "ZERO", "balance": "0", "locked": "0", "avg_buy_price": "5", "unit_currency": "KRW"},
    ]
    monkeypatch.setattr(trading_engine, "private_upbit", lambda *_: accounts)
    monkeypatch.setattr(trading_engine, "upbit_public", lambda *_: [
        {"market": "KRW-BTC", "trade_price": 12000}, {"market": "KRW-ETH", "trade_price": 1000},
    ])
    result = trading_engine.account_snapshot("test", "test")
    assert result["total_valuation"] == 33000
    assert result["valuation_complete"] is False
    assert result["unpriced_currencies"] == ["OLD"]
    assert [row["currency"] for row in result["assets"]] == ["BTC", "KRW", "ETH", "OLD"]
    by_currency = {row["currency"]: row for row in result["assets"]}
    assert by_currency["BTC"]["profit_rate"] == 20
    assert by_currency["BTC"]["quantity"] == 2
    assert by_currency["OLD"]["current_price"] is None
    assert by_currency["OLD"]["valuation"] is None
    assert by_currency["OLD"]["profit_rate"] is None
    assert by_currency["ETH"]["purchase_amount"] is None
    assert by_currency["ETH"]["profit_rate"] is None


def test_empty_account_snapshot_is_complete(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine, "private_upbit", lambda *_: [])
    monkeypatch.setattr(trading_engine, "upbit_public", lambda *_: [])
    assert trading_engine.account_snapshot("test", "test") == {
        "total_valuation": 0, "valuation_complete": True, "unpriced_currencies": [], "assets": [],
    }


@pytest.mark.parametrize("all_failed", [False, True])
def test_recommendation_quote_failures_do_not_block_other_positions(trading_engine, monkeypatch, all_failed):
    template = {"name": "Test", "expected_selling_price": 120, "minimum_selling_price": 90,
                "temp_price": 100, "setting_price": 100, "renewal_cnt": 0}
    monkeypatch.setattr(trading_engine, "setting", lambda *_: {"expected_high_percentage": 10, "expected_low_percentage": -5})
    monkeypatch.setattr(trading_engine.db, "all", lambda *_: [{**template, "code": "BAD"}, {**template, "code": "GOOD"}])
    requests, errors = [], []
    monkeypatch.setattr(trading_engine, "record_error", lambda *args: errors.append(args))
    def quotes(code, count):
        if code == "BAD" or all_failed:
            raise httpx.ConnectError("test quote failure")
        return [{"close": 110, "high": 112, "low": 105, "volume": 1}]
    def calculate(endpoint, payload):
        requests.append(payload)
        return {"positions": []}
    monkeypatch.setattr(trading_engine, "calc", calculate)
    trading_engine._update_positions("upbit", quotes)
    assert len(errors) == (2 if all_failed else 1)
    assert errors[0][:2] == ("UPBIT", "UPDATE_PRICE_ITEM")
    if all_failed:
        assert not requests
    else:
        assert [p["code"] for p in requests[0]["positions"]] == ["GOOD"]
