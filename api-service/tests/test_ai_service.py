import os
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
            self.result = self.database.row
        elif query.startswith("DELETE FROM ai_analyses"):
            self.database.deleted = params

    def fetchone(self): return self.result


class DeleteConnection:
    def __init__(self, database): self.database = database
    def cursor(self): return DeleteCursor(self.database)


class DeleteDatabase:
    def __init__(self, row):
        self.row, self.deleted, self.queries = row, None, []

    @contextmanager
    def connection(self):
        yield DeleteConnection(self)


@pytest.mark.parametrize("row,message", [
    ({"status": "RUNNING", "applied_candidate_id": None}, "진행 중"),
    ({"status": "COMPLETED", "applied_candidate_id": "candidate-1"}, "감사 기록"),
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
