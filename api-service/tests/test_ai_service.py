import os
from contextlib import contextmanager

import pytest
from cryptography.fernet import InvalidToken
from pydantic import ValidationError
from fastapi import HTTPException

os.environ.setdefault("SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-characters")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

from app.ai import AIService, AnalysisRequest, ConfigUpdate, account_for_ai, candidate_verified, key_cipher
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
