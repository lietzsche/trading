import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_select_empty_instruments():
    res = client.post("/v1/recommendations/select", json={"instruments": []})
    assert res.status_code == 200
    assert res.json()["selected_codes"] == []


def test_select_deduplication():
    candles = [{"close": 100.0} for _ in range(41)]
    inst = {"code": "KRW-BTC", "prices": candles}
    res = client.post("/v1/recommendations/select", json={"instruments": [inst, inst]})
    assert res.status_code == 200
    assert res.json()["selected_codes"] == ["KRW-BTC"]  # Deduplicated to 1 item


def test_select_nan_and_inf_rejected():
    # JSON doesn't support NaN directly, but null or strings or raw floats
    res_str = client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-BTC", "prices": [{"close": "not_a_number"}]}]
    })
    assert res_str.status_code == 422

    res_neg = client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-BTC", "prices": [{"close": -10.0}]}]
    })
    assert res_neg.status_code == 422


def test_select_period_boundaries():
    # ma_period min is 2, max is 199
    # Period 1 must be rejected with 422
    candles_3 = [{"close": 100.0} for _ in range(3)]
    res_p1 = client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-BTC", "prices": candles_3, "ma_period": 1}]
    })
    assert res_p1.status_code == 422

    # Period 200 must be rejected with 422
    res_p200 = client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-BTC", "prices": candles_3, "ma_period": 200}]
    })
    assert res_p200.status_code == 422

    # Period 2 is valid (requires 3 candles: 1 forming + 2 completed)
    res_p2 = client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-BTC", "prices": candles_3, "ma_period": 2}]
    })
    assert res_p2.status_code == 200
    assert res_p2.json()["selected_codes"] == ["KRW-BTC"]


def test_auto_trade_hold_invariant():
    """When held asset is in recommendations, no SELL or BUY action is emitted."""
    res = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": ["KRW-BTC", "KRW-ETH"],
        "balances": [{"currency": "KRW"}, {"currency": "BTC"}]
    })
    assert res.status_code == 200
    # BTC is held and in recommendations -> held list is ["KRW-BTC"], actions is []
    assert res.json()["actions"] == []


def test_auto_trade_partial_sell():
    """Held asset not in recommendations is sold; recommended held asset is kept."""
    res = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": ["KRW-ETH"],
        "balances": [{"currency": "KRW"}, {"currency": "BTC"}, {"currency": "ETH"}]
    })
    assert res.status_code == 200
    # BTC is not in recommendations -> SELL KRW-BTC
    # ETH is in recommendations -> kept
    assert res.json()["actions"] == [{"side": "SELL", "market": "KRW-BTC"}]


def test_auto_trade_cash_immunity():
    """KRW balance must never emit a SELL action."""
    res = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": [],
        "balances": [{"currency": "KRW"}]
    })
    assert res.status_code == 200
    assert res.json()["actions"] == []


def test_backtest_unsorted_candles_auto_sorting():
    """Candles supplied in reverse date order must be sorted ascending before simulation."""
    candles = [
        {"date": "2026-01-05", "open": 110, "close": 110},
        {"date": "2026-01-01", "open": 100, "close": 100},
        {"date": "2026-01-03", "open": 100, "close": 100},
        {"date": "2026-01-02", "open": 100, "close": 100},
        {"date": "2026-01-04", "open": 100, "close": 100},
    ]
    res = client.post("/v1/backtests/ma40", json={
        "candles": candles,
        "ma_period": 2,
        "initial_capital": 1000000,
        "fee_bps": 5,
        "slippage_bps": 10
    })
    assert res.status_code == 200
    data = res.json()
    # Curve must follow chronological order
    curve_dates = [c["date"] for c in data["curve"]]
    assert curve_dates == sorted(curve_dates)
