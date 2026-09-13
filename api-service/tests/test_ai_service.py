import os

import pytest
from cryptography.fernet import InvalidToken
from pydantic import ValidationError

os.environ.setdefault("SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-characters")
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")

from app.ai import AIService, AnalysisRequest, ConfigUpdate, candidate_verified, key_cipher
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


def test_only_sufficiently_validated_non_current_candidate_can_apply():
    assert candidate_verified({"id": "candidate-1", "validation": {"days": 10, "trades": 1}})
    assert not candidate_verified({"id": "current", "validation": {"days": 20, "trades": 2}})
    assert not candidate_verified({"id": "candidate-1", "validation": {"days": 9, "trades": 2}})
    assert not candidate_verified({"id": "candidate-1", "validation": {"days": 20, "trades": 0}})
