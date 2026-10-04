import os
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import httpx
import pytest
from cryptography.fernet import InvalidToken
from pydantic import ValidationError
from fastapi import HTTPException

os.environ.setdefault("SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-characters")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

from app.ai import AIService, AnalysisRequest, AutomationUpdate, ConfigUpdate, account_for_ai, candidate_verified, key_cipher
from app.main import SettingUpdate


@pytest.mark.parametrize("drawdown,returns,expected", [(8.42, 11, False), (7.90, 11, True), (2.00, 11, True), (2.00, 10, False), (2.00, 9, False)])
def test_auto_apply_drawdown_and_return_gate(drawdown, returns, expected):
    from app.ai import auto_apply_eligible
    baseline = {"id": "current", "validation": {"return_pct": 10, "max_drawdown_pct": 5.93}}
    candidate = {"id": "candidate-1", "validation": {"days": 20, "trades": 3, "return_pct": returns, "max_drawdown_pct": drawdown}}
    assert auto_apply_eligible(candidate, baseline) is expected


def test_auto_apply_rejects_missing_nonfinite_and_negative_metrics():
    from app.ai import auto_apply_eligible
    baseline = {"validation": {"return_pct": 10, "max_drawdown_pct": 5.93}}
    for drawdown in (None, float("nan"), float("inf"), -1):
        assert not auto_apply_eligible({"id": "candidate-1", "validation": {"days": 20, "trades": 3, "return_pct": 11, "max_drawdown_pct": drawdown}}, baseline)


SETTINGS_BEFORE = {"expected_high_percentage": 20, "expected_low_percentage": -10, "highest_price_reference_days": 30, "volume_check": False}
SETTINGS_AFTER = {**SETTINGS_BEFORE, "expected_high_percentage": 25}

def test_stock_context_includes_currency_in_recommendations_and_history():
    class ContextDB:
        def all(self,sql,params=()):
            if 'trade_error_log' in sql:return []
            return [{'code':'US:AAPL','temp_price':120},{'code':'005930','temp_price':60000}]
    service=AIService(lambda:ContextDB(),None,'http://calculation',os.environ['SESSION_SECRET'],SettingUpdate)
    context=service._context({'market':'stock','include_account':False,'settings_snapshot':SETTINGS_BEFORE},{'user_login_id':'test'})
    for key in ('recommendations','recommendation_history'):
        assert context[key][0]['currency']=='USD' and context[key][0]['market_region']=='US'
        assert context[key][1]['currency']=='KRW' and context[key][1]['market_region']=='KR'


class SafetyCursor:
    def __init__(self, database): self.database, self.result = database, None
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, query, params=()):
        self.database.writes.append((query, params))
        if "SELECT a.*" in query or query.startswith("SELECT * FROM ai_analyses"):
            self.result = self.database.analysis
        elif "FROM deal_settings" in query:
            self.result = self.database.current
        elif "max(applied_at)" in query:
            self.result = {"last_applied_at": self.database.last_applied}
    def fetchone(self): return self.result


class SafetyDatabase:
    def __init__(self, last_applied=None, current=None):
        self.writes, self.last_applied = [], last_applied
        self.current = current or SETTINGS_BEFORE
        self.analysis = {"id": 11, "user_id": 7, "market": "upbit", "auto_apply_settings": True,
                         "settings_snapshot": SETTINGS_BEFORE, "applied_candidate_id": None, "reverted_at": None}
    @contextmanager
    def connection(self): yield self
    def cursor(self): return SafetyCursor(self)
    def execute(self, query, params=()): self.writes.append((query, params))


@pytest.mark.parametrize("hours,allowed", [(1, False), (73, True)])
def test_auto_apply_cooldown_blocks_recent_and_allows_elapsed(hours, allowed):
    database = SafetyDatabase(last_applied=datetime.now(timezone.utc)-timedelta(hours=hours))
    result = {"candidates": [
        {"id": "current", "validation": {"return_pct": 10, "max_drawdown_pct": 5.93}},
        {"id": "candidate-1", "settings": SETTINGS_AFTER, "validation": {"days": 20, "trades": 3, "return_pct": 11, "max_drawdown_pct": 7.90}}]}
    service(database)._auto_apply_verified_settings(11, result)
    assert any(query.startswith("UPDATE deal_settings") for query, _ in database.writes) is allowed
    if not allowed:
        assert any("최근 자동 적용 후 대기 시간" in str(params) for _, params in database.writes)
    assert any("FOR UPDATE" in query and "deal_settings" in query for query, _ in database.writes)


def test_automation_fingerprint_ignores_live_price_changes():
    class Database:
        price = 100
        def one(self, *_): return SETTINGS_BEFORE
        def all(self, *_): return [{"code": "KRW-BTC", "renewal_cnt": 1, "temp_price": self.price, "minimum_selling_price": 90, "expected_selling_price": 120}]
    database = Database()
    instance = service(database)
    before = instance._automation_fingerprint()
    database.price = 110
    assert instance._automation_fingerprint() == before


@pytest.mark.parametrize("minutes,expected_launches", [(0, 0), (61, 1)])
def test_recommendation_change_respects_minimum_interval(minutes, expected_launches):
    class Database:
        def all(self, *_): return [{"user_id": 7, "trigger_mode": "recommendation_change", "last_started_at": datetime.now(timezone.utc)-timedelta(minutes=minutes), "interval_minutes": 60}]
    instance = service(Database())
    launched = []
    instance._launch_automation = lambda config: launched.append(config)
    instance.automation_tick()
    assert len(launched) == expected_launches


@pytest.mark.parametrize("changed", [False, True])
def test_revert_restores_snapshot_only_when_current_matches_applied(changed):
    database = SafetyDatabase(current=SETTINGS_BEFORE if changed else SETTINGS_AFTER)
    database.analysis.update(applied_candidate_id="candidate-1", result={"candidates": [{"id": "candidate-1", "settings": SETTINGS_AFTER}]})
    if changed:
        with pytest.raises(HTTPException) as error:
            service(database).revert(7, 11)
        assert error.value.status_code == 409
        assert not any(query.startswith("UPDATE") for query, _ in database.writes)
    else:
        assert service(database).revert(7, 11)["settings"] == SETTINGS_BEFORE
        updates = [(query, params) for query, params in database.writes if query.startswith("UPDATE")]
        assert updates[0][1] == (*SETTINGS_BEFORE.values(), "upbit")
        assert "reverted_at=now()" in updates[1][0]
    assert any("deal_settings" in query and "FOR UPDATE" in query for query, _ in database.writes)


def test_revert_rejects_repeated_and_foreign_analysis():
    database = SafetyDatabase()
    database.analysis = None
    with pytest.raises(HTTPException) as error:
        service(database).revert(7, 11)
    assert error.value.status_code == 404
    database.analysis = {"applied_candidate_id": "candidate-1", "reverted_at": datetime.now(timezone.utc)}
    with pytest.raises(HTTPException) as error:
        service(database).revert(7, 11)
    assert error.value.status_code == 409


class CaptureDatabase:
    def __init__(self):
        self.writes = []

    def execute(self, query, params=()):
        self.writes.append((query, params))

    def one(self, query, params=()):
        return None


def service(database):
    return AIService(lambda: database, object(), "http://calculation", os.environ["SESSION_SECRET"], SettingUpdate)


def test_key_cipher_is_owner_scoped_and_detects_tampering():
    encrypted = key_cipher(os.environ["SESSION_SECRET"], 1).encrypt(b"provider-secret")
    assert key_cipher(os.environ["SESSION_SECRET"], 1).decrypt(encrypted) == b"provider-secret"
    with pytest.raises(InvalidToken):
        key_cipher(os.environ["SESSION_SECRET"], 2).decrypt(encrypted)


def test_saved_provider_key_is_encrypted_and_only_hint_is_retained():
    database = CaptureDatabase()
    raw = "sk-test-provider-secret-1234"
    service(database).save_config(7, ConfigUpdate(api_key=raw))
    _, params = database.writes[0]
    assert raw not in params[1]
    assert params[2] == "…1234"
    assert key_cipher(os.environ["SESSION_SECRET"], 7).decrypt(params[1].encode()).decode() == raw


def test_market_defaults_and_symbol_validation_are_explicit():
    assert AnalysisRequest(market="upbit").fee_bps == 5
    assert AnalysisRequest(market="stock").fee_bps == 15
    assert AnalysisRequest(market="stock",symbols=["AAPL"]).symbols==["US:AAPL"]
    with pytest.raises(ValidationError):
        AnalysisRequest(market="stock", symbols=["KRW-BTC"])
    with pytest.raises(ValidationError):
        AnalysisRequest(market="upbit", symbols=["BTC"])


def test_ai_automation_has_bounded_explicit_options():
    payload = AutomationUpdate(enabled=True, trigger_mode="recommendation_change",
                               interval_minutes=120, auto_apply_settings=True)
    assert payload.interval_minutes == 120 and payload.auto_apply_settings is True
    with pytest.raises(ValidationError):
        AutomationUpdate(enabled=True, interval_minutes=59)
    with pytest.raises(ValidationError):
        AutomationUpdate(enabled=True, trigger_mode="price_tick")


def test_account_for_ai_hides_non_krw_avg_buy_price():
    # A non-KRW avg_buy_price is on a different scale than KRW daily closes
    # (e.g. legacy BTC-quoted holdings); the model must never see it as if it
    # were comparable to a KRW price.
    krw = account_for_ai({"currency": "BTC", "balance": "1", "locked": "0",
                           "avg_buy_price": "10000", "unit_currency": "KRW"})
    assert krw["avg_buy_price"] == "10000"
    assert krw["avg_buy_price_note"] is None

    non_krw = account_for_ai({"currency": "ETH", "balance": "3", "locked": "0",
                               "avg_buy_price": "0.01", "unit_currency": "BTC"})
    assert non_krw["avg_buy_price"] is None
    assert non_krw["avg_buy_price_unit_currency"] == "BTC"
    assert "KRW" in non_krw["avg_buy_price_note"]


class StubFillsEngine:
    def __init__(self, fills, failures=()):
        self.fills, self.failures = fills, set(failures)

    def order_fills(self, access, secret, uuid):
        if uuid in self.failures:
            raise httpx.HTTPError("boom")
        return self.fills.get(uuid, [])


def test_realized_pnl_fifo_matches_sells_across_multiple_buy_lots():
    engine = StubFillsEngine({
        "buy1": [{"volume": "2", "funds": "20000"}],
        "buy2": [{"volume": "3", "funds": "36000"}],
        "sell1": [{"volume": "4", "funds": "52000"}],
    })
    service_instance = AIService(lambda: CaptureDatabase(), engine, "http://calculation", os.environ["SESSION_SECRET"], SettingUpdate)
    orders = [  # newest-first, as returned by the real order-history query
        {"uuid": "sell1", "market": "KRW-BTC", "side": "ask", "state": "done", "paid_fee": "26"},
        {"uuid": "buy2", "market": "KRW-BTC", "side": "bid", "state": "done", "paid_fee": "18"},
        {"uuid": "buy1", "market": "KRW-BTC", "side": "bid", "state": "done", "paid_fee": "10"},
    ]
    summary = service_instance._realized_pnl_summary({"access_key": "a", "secret_key": "s"}, orders)
    market = summary["per_market"]["KRW-BTC"]
    assert market["realized_krw"] == 7952.0
    assert market["matched_volume"] == 4
    assert market["unmatched_sell_volume"] == 0
    assert market["closed_sell_fills"] == 1
    assert summary["orders_examined"] == 3 and summary["orders_unavailable"] == []


def test_realized_pnl_tracks_unmatched_sells_and_unavailable_orders():
    engine = StubFillsEngine({
        "sell1": [{"volume": "5", "funds": "50000"}],
        "buy1": [{"volume": "1", "funds": "9000"}],
    }, failures={"buy2"})
    service_instance = AIService(lambda: CaptureDatabase(), engine, "http://calculation", os.environ["SESSION_SECRET"], SettingUpdate)
    orders = [
        {"uuid": "sell1", "market": "KRW-ETH", "side": "ask", "state": "done", "paid_fee": "0"},
        {"uuid": "buy2", "market": "KRW-ETH", "side": "bid", "state": "done", "paid_fee": "0"},
        {"uuid": "buy1", "market": "KRW-ETH", "side": "bid", "state": "done", "paid_fee": "0"},
        {"uuid": None, "market": "KRW-XRP", "side": "bid", "state": "done", "paid_fee": "0"},
        {"uuid": "wait1", "market": "KRW-DOGE", "side": "bid", "state": "wait", "paid_fee": "0"},
    ]
    summary = service_instance._realized_pnl_summary({"access_key": "a", "secret_key": "s"}, orders)
    market = summary["per_market"]["KRW-ETH"]
    assert market["matched_volume"] == 1 and market["unmatched_sell_volume"] == 4
    assert summary["orders_unavailable"] == ["KRW-ETH"]
    assert "KRW-XRP" not in summary["per_market"] and "KRW-DOGE" not in summary["per_market"]


def test_only_sufficiently_validated_non_current_candidate_can_apply():
    assert candidate_verified({"id": "candidate-1", "validation": {"days": 10, "trades": 1}})
    assert not candidate_verified({"id": "current", "validation": {"days": 20, "trades": 2}})
    assert not candidate_verified({"id": "candidate-1", "validation": {"days": 9, "trades": 2}})
    assert not candidate_verified({"id": "candidate-1", "validation": {"days": 20, "trades": 0}})


class DeleteCursor:
    def __init__(self, database):
        self.database, self.result = database, None

    def __enter__(self): return self
    def __exit__(self, *_): return False

    def execute(self, query, params=()):
        self.database.queries.append((query, params))
        if query.startswith("SELECT status"):
            self.result = self.database.rows.get(params[0]) if self.database.rows is not None else self.database.row
        elif query.startswith("SELECT 1 FROM ai_conversation_messages"):
            self.result = {"exists": 1} if params[0] in self.database.running_messages else None
        elif query.startswith("DELETE FROM ai_analyses"):
            self.database.deleted = params
        elif query.startswith("UPDATE ai_analyses SET hidden_at"):
            self.database.hidden = params

    def fetchone(self): return self.result


class DeleteConnection:
    def __init__(self, database): self.database = database
    def cursor(self): return DeleteCursor(self.database)


class DeleteDatabase:
    def __init__(self, row, running_messages=(), rows=None):
        self.row, self.deleted, self.hidden, self.queries = row, None, None, []
        self.running_messages, self.rows = set(running_messages), rows

    @contextmanager
    def connection(self):
        yield DeleteConnection(self)


@pytest.mark.parametrize("row,message", [
    ({"status": "RUNNING", "applied_candidate_id": None}, "진행 중"),
    (None, "찾을 수"),
])
def test_conversation_delete_protects_active_applied_and_foreign_records(row, message):
    database = DeleteDatabase(row)
    with pytest.raises(HTTPException, match=message):
        service(database).delete_analysis(7, 11)
    assert database.deleted is None


def test_completed_unapplied_conversation_can_be_deleted_by_owner():
    database = DeleteDatabase({"status": "COMPLETED", "applied_candidate_id": None})
    service(database).delete_analysis(7, 11)
    assert database.deleted == (11, 7)


def test_applied_conversation_is_hidden_but_preserved_for_audit():
    database = DeleteDatabase({"status": "COMPLETED", "applied_candidate_id": "candidate-1"})
    service(database).delete_analysis(7, 11)
    assert database.hidden == (11, 7)
    assert database.deleted is None


def test_conversation_with_running_followup_cannot_be_deleted():
    database = DeleteDatabase({"status": "COMPLETED", "applied_candidate_id": None}, running_messages=[11])
    with pytest.raises(HTTPException) as error:
        service(database).delete_analysis(7, 11)
    assert error.value.status_code == 409
    assert error.value.detail == "후속 답변이 진행 중인 대화는 삭제할 수 없습니다."
    assert database.deleted is None and database.hidden is None


def test_bulk_delete_mixed_owner_scoped_records():
    database = DeleteDatabase(None, running_messages=[4], rows={
        1: {"status": "COMPLETED", "applied_candidate_id": None},
        2: {"status": "COMPLETED", "applied_candidate_id": "candidate-1"},
        3: {"status": "RUNNING", "applied_candidate_id": None},
        4: {"status": "COMPLETED", "applied_candidate_id": None},
        # 5 belongs to another user and is excluded by the owner query.
    })
    result = service(database).bulk_delete_analyses(7, [1, 2, 3, 4, 5, 1])
    assert result == {"deleted": 1, "hidden": 1, "skipped": [{"id": 3, "reason": "running"}, {"id": 4, "reason": "running"}]}
    assert database.deleted == (1, 7) and database.hidden == (2, 7)
    assert all(params[1] == 7 and "user_id=%s" in query and "FOR UPDATE" in query
               for query, params in database.queries if query.startswith("SELECT status"))


def test_bulk_delete_rejects_empty_oversized_or_invalid_ids():
    from app.ai import BulkDeleteRequest
    for ids in ([], list(range(1, 52)), [0], [-1]):
        with pytest.raises(ValidationError):
            BulkDeleteRequest(ids=ids)
