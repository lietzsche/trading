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


def test_live_signal_accepts_a_period_per_instrument():
    short = bars(101)[:6]
    response=client.post('/v1/recommendations/select',json={
        'instruments':[{'code':'KRW-BTC','prices':short,'ma_period':5}]})
    assert response.json()['selected_codes']==['KRW-BTC']


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


def test_backtest_uses_next_open_and_reports_costs():
    candles=[]
    for index in range(45):
        close=100 if index < 41 else 110
        candles.append({"date":f"2026-01-{index+1:02d}","open":120 if index==41 else close,"close":close})
    result=client.post('/v1/backtests/ma40',json={"candles":candles,"initial_capital":1000000,"ma_period":40,
        "fee_bps":5,"slippage_bps":10}).json()
    assert result['ma_period']==40
    assert result['trades'][0]['side']=='BUY' and result['trades'][0]['price']==120*1.001
    assert result['trade_count']==1 and result['final_equity'] < 1000000
    assert 'benchmark_return_pct' in result and 'excess_return_pct' in result


def test_backtest_accepts_a_configurable_moving_average_period():
    candles=[{"date":f"2026-02-{index+1:02d}","open":100,"close":100 if index<6 else 110}
             for index in range(10)]
    result=client.post('/v1/backtests/ma40',json={"candles":candles,"ma_period":5}).json()
    assert result['ma_period']==5
    assert result['trade_count']==1
