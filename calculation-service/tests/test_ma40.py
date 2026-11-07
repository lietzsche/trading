from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def bars(current, completed=100):
    row = lambda close: {"close": close, "high": close, "low": close, "volume": 1}
    return [row(current), *[row(completed) for _ in range(40)]]


def select(prices):
    return client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-BTC", "prices": prices}],
    }).json()["selected_codes"]


def test_uses_current_price_against_40_completed_candles():
    assert select(bars(100)) == ["KRW-BTC"]
    assert select(bars(99)) == []


def test_requires_40_completed_candles_and_rejects_zero_prices():
    assert select(bars(101)[:-1]) == []
    invalid = bars(101)
    invalid[20]["close"] = 0
    assert select(invalid) == []


def test_today_candle_is_not_part_of_the_average():
    # If today's 1000 were included, the mean would exceed the current price.
    assert select(bars(1000, 100)) == ["KRW-BTC"]


def test_auto_trade_buys_with_one_signal_and_sells_below_ma40():
    buy = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": ["KRW-BTC"], "balances": [{"currency": "KRW"}]
    }).json()
    sell = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": [], "balances": [{"currency": "BTC"}]
    }).json()
    assert buy == {"actions": [{"side": "BUY", "market": "KRW-BTC"}]}
    assert sell == {"actions": [{"side": "SELL", "market": "KRW-BTC"}]}
