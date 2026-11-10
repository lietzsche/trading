from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_backtest_win_rate_pct_is_returned_and_accurate():
    # Build a candle series with 1 winning trade and 1 losing trade (ma_period=5)
    # Days 0..4: close=100 (5 history bars)
    # Day 5: close=110 >= 100 -> Day 6 BUY at open=110
    # Day 6: close=150 >= avg -> hold
    # Day 7: close=80 < avg -> Day 8 SELL at open=140 (winning trade: 140 > 110)
    # Day 8: close=80 < avg
    # Day 9: close=200 >= avg -> Day 10 BUY at open=200
    # Day 10: close=150 (final forced SELL at close=150 < 200 -> losing trade)
    closes = [100, 100, 100, 100, 100, 110, 150, 80, 80, 200, 150]
    opens = [100, 100, 100, 100, 100, 110, 110, 150, 140, 200, 200]
    candles = [
        {"date": f"2026-01-{idx + 1:02d}", "open": opens[idx], "close": closes[idx]}
        for idx in range(len(closes))
    ]
    res = client.post(
        "/v1/backtests/ma40",
        json={
            "candles": candles,
            "ma_period": 5,
            "initial_capital": 1_000_000,
            "fee_bps": 5,
            "slippage_bps": 10,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "win_rate_pct" in body
    assert body["trade_count"] == 2
    assert body["win_rate_pct"] == 50.0


def test_backtest_win_rate_pct_zero_when_no_trades():
    candles = [
        {"date": f"2026-01-{idx + 1:02d}", "open": 100 - idx, "close": 100 - idx}
        for idx in range(10)
    ]
    res = client.post("/v1/backtests/ma40", json={"candles": candles, "ma_period": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["trade_count"] == 0
    assert body["win_rate_pct"] == 0.0
