import hashlib
from urllib.parse import urlencode

import jwt

from app.trading import TradingEngine


class NoopDatabase:
    def execute(self, *_):
        pass


def test_upbit_order_token_contains_matching_query_hash():
    params = {"market": "KRW-BTC", "side": "bid", "price": "5000", "ord_type": "price"}
    token = TradingEngine.token("access", "secret", params)
    claims = jwt.decode(token, "secret", algorithms=["HS256"])
    assert claims["access_key"] == "access"
    assert claims["query_hash"] == hashlib.sha512(urlencode(params).encode()).hexdigest()
    assert claims["query_hash_alg"] == "SHA512"


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
