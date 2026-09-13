from copy import deepcopy
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.backtest import Candidate, HistoricalInstrument, _portfolio_metrics, _simulate_segment


client = TestClient(app)


def candles(count=100):
    # Repeat a rise and fall so both entry and exit paths execute.
    values = [100, 104, 109, 115, 121, 130, 120, 106, 98, 99]
    return [
        {"date": (date(2024, 1, 1) + timedelta(days=index)).isoformat(),
         "open": values[index % 10], "high": values[index % 10] + 1,
         "low": values[index % 10] - 1, "close": values[index % 10], "volume": 100}
        for index in range(count)
    ]


def settings(**changes):
    return {"id": "current", "label": "현재 설정", "expected_high_percentage": 10,
            "expected_low_percentage": -5, "highest_price_reference_days": 3,
            "volume_check": False, **changes}


def payload(**changes):
    return {"market": "upbit", "instruments": [{"code": "KRW-TEST", "name": "테스트", "prices": candles()}],
            "candidates": [settings()], "fee_bps": 5, "slippage_bps": 10, **changes}


def test_comparison_is_deterministic_and_reports_dates_and_costs():
    first = client.post("/v1/backtests/compare", json=payload())
    second = client.post("/v1/backtests/compare", json=payload())
    assert first.status_code == 200
    assert first.json() == second.json()
    data = first.json()
    assert len(data["dataset"]["data_sha256"]) == 64
    assert data["dataset"]["warmup_days"] == 3
    assert data["dataset"]["train_days"] == 67
    assert data["dataset"]["validation_days"] == 30
    assert data["dataset"]["train_end"] < data["dataset"]["validation_start"]
    assert data["dataset"]["fee_bps"] == 5
    assert data["dataset"]["slippage_bps"] == 10
    assert data["candidates"][0]["validation"]["trades"] > 0
    assert data["candidates"][0]["validation"]["max_drawdown_pct"] >= 0
    assert any("미래 수익" in value for value in data["limitations"])


def test_reverse_input_dates_are_normalized_without_changing_results():
    request = payload()
    expected = client.post("/v1/backtests/compare", json=request).json()
    request["instruments"][0]["prices"].reverse()
    actual = client.post("/v1/backtests/compare", json=request).json()
    assert actual == expected


def test_candidates_share_maximum_warmup_and_same_evaluation_dates():
    request = payload(candidates=[settings(), settings(id="other", label="다른 설정", highest_price_reference_days=20)])
    response = client.post("/v1/backtests/compare", json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["dataset"]["warmup_days"] == 20
    assert {item["train"]["days"] for item in data["candidates"]} == {56}
    assert {item["validation"]["days"] for item in data["candidates"]} == {24}


def test_changing_validation_prices_cannot_change_training_result():
    request = payload()
    original = client.post("/v1/backtests/compare", json=request).json()
    validation_start = original["dataset"]["validation_start"]
    for row in request["instruments"][0]["prices"]:
        if row["date"] >= validation_start:
            for key in ("open", "high", "low", "close"):
                row[key] *= 10
    changed = client.post("/v1/backtests/compare", json=request).json()
    assert changed["candidates"][0]["train"] == original["candidates"][0]["train"]
    assert changed["dataset"]["data_sha256"] != original["dataset"]["data_sha256"]


@pytest.mark.parametrize("costs", [(0, 0), (5, 10), (100, 100)])
def test_fills_at_next_open_and_charges_both_sides_without_intraday_stop(costs):
    rows = candles(6)
    for row, opening, close, low in zip(rows, [100, 105, 110, 120, 100, 90], [100, 105, 110, 110, 100, 90], [99, 104, 109, 80, 99, 89]):
        row.update(open=opening, close=close, high=max(opening, close) + 1, low=low)
    instrument = HistoricalInstrument(code="KRW-TEST", prices=rows)
    fee, slippage = [value / 10_000 for value in costs]
    result = _simulate_segment(instrument, Candidate(**settings()), "upbit",
                               date(2024, 1, 4), date(2024, 1, 6), fee, slippage)
    # Signal close was 110 but the entry was next open 120. Day 4 low 80
    # does not create an intraday stop; day 5 close 100 exits at day 6 open 90.
    expected = 90 * (1 - slippage) * (1 - fee) / (120 * (1 + slippage) * (1 + fee))
    assert result["curve"][date(2024, 1, 6)] == pytest.approx(expected)
    assert result["buys"] == result["sells"] == 1
    assert result["open_positions"] == 0


def test_zero_volume_bar_does_not_fill_pending_order():
    rows = candles(5)
    for row, value in zip(rows, [100, 105, 110, 120, 125]):
        row.update(open=value, close=value, high=value + 1, low=value - 1)
    rows[3]["volume"] = 0
    result = _simulate_segment(HistoricalInstrument(code="KRW-TEST", prices=rows), Candidate(**settings()), "upbit",
                               date(2024, 1, 4), date(2024, 1, 5), 0, 0)
    assert result["curve"][date(2024, 1, 4)] == 1
    assert result["curve"][date(2024, 1, 5)] == 1
    assert result["buys"] == 1


def test_validation_resets_cash_and_positions_but_uses_past_for_warmup():
    request = payload()
    response = client.post("/v1/backtests/compare", json=request).json()
    dataset = response["dataset"]
    instrument = HistoricalInstrument(**request["instruments"][0])
    simulation = _simulate_segment(instrument, Candidate(**settings()), "upbit",
                                    date.fromisoformat(dataset["validation_start"]),
                                    date.fromisoformat(dataset["validation_end"]), 5 / 10_000, 10 / 10_000)
    assert response["candidates"][0]["validation"] == _portfolio_metrics([simulation])


def test_portfolio_drawdown_comes_from_combined_daily_equity_not_average_drawdowns():
    day1, day2 = date(2024, 1, 1), date(2024, 1, 2)
    metrics = _portfolio_metrics([
        {"curve": {day1: 2, day2: 1}, "buys": 1, "sells": 0, "open_positions": 1},
        {"curve": {day1: 0.5, day2: 1}, "buys": 1, "sells": 0, "open_positions": 1},
    ])
    assert metrics["return_pct"] == 0
    assert metrics["max_drawdown_pct"] == 20
    assert metrics["buys"] == 2


def test_missing_instrument_dates_are_marked_and_equity_carries_forward():
    request = payload()
    second = deepcopy(request["instruments"][0])
    second["code"] = "KRW-OTHER"
    second["prices"].pop(50)
    request["instruments"].append(second)
    response = client.post("/v1/backtests/compare", json=request)
    assert response.status_code == 200
    assert any("공백" in warning for warning in response.json()["warnings"])
    assert len(response.json()["candidates"][0]["per_instrument"]) == 2


@pytest.mark.parametrize("field,value", [
    ("expected_high_percentage", 0), ("expected_high_percentage", 1001),
    ("expected_low_percentage", -100), ("expected_low_percentage", 10),
    ("highest_price_reference_days", 2), ("highest_price_reference_days", 201),
])
def test_invalid_candidates_are_rejected(field, value):
    request = payload(candidates=[settings(**{field: value})])
    assert client.post("/v1/backtests/compare", json=request).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("open", 0), ("close", -1), ("low", 110), ("high", 90),
    ("close", "NaN"), ("volume", -1), ("volume", "Infinity"), ("date", "bad-date"),
])
def test_invalid_candles_are_rejected(field, value):
    request = payload()
    request["instruments"][0]["prices"][0][field] = value
    assert client.post("/v1/backtests/compare", json=request).status_code == 422


@pytest.mark.parametrize("field,value", [("fee_bps", -1), ("fee_bps", 101), ("slippage_bps", "NaN")])
def test_invalid_costs_are_rejected(field, value):
    assert client.post("/v1/backtests/compare", json=payload(**{field: value})).status_code == 422


@pytest.mark.parametrize("duplicate", ["instrument", "date", "candidate"])
def test_duplicate_data_and_identifiers_are_rejected(duplicate):
    request = payload()
    if duplicate == "instrument":
        request["instruments"].append(request["instruments"][0])
    elif duplicate == "date":
        request["instruments"][0]["prices"][1]["date"] = request["instruments"][0]["prices"][0]["date"]
    else:
        request["candidates"].append(request["candidates"][0])
    assert client.post("/v1/backtests/compare", json=request).status_code == 422


@pytest.mark.parametrize("count,reference", [(32, 3), (200, 180)])
def test_insufficient_common_warmup_and_evaluation_is_explicit_error(count, reference):
    request = payload(candidates=[settings(highest_price_reference_days=reference)])
    request["instruments"][0]["prices"] = candles(count)
    response = client.post("/v1/backtests/compare", json=request)
    assert response.status_code == 422
    assert "자료가 부족" in response.json()["detail"]


@pytest.mark.parametrize("kind", ["bars", "instruments", "candidates"])
def test_request_work_is_bounded(kind):
    request = payload()
    if kind == "bars":
        request["instruments"][0]["prices"] = candles(201)
    elif kind == "instruments":
        request["instruments"] = [{**request["instruments"][0], "code": f"KRW-{index}"} for index in range(6)]
    else:
        request["candidates"] = [settings(id=str(index)) for index in range(5)]
    assert client.post("/v1/backtests/compare", json=request).status_code == 422


def test_no_trade_and_short_validation_warnings_are_not_hidden():
    request = payload(candidates=[settings(volume_check=True)])
    request["instruments"][0]["prices"] = candles(33)
    response = client.post("/v1/backtests/compare", json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["candidates"][0]["validation"]["return_pct"] == 0
    assert data["candidates"][0]["validation"]["days"] == 9
    assert any("청산 완료 거래가 없어" in warning for warning in data["warnings"])
    assert any("30봉 미만" in warning for warning in data["warnings"])


@pytest.mark.parametrize("market,fee", [("upbit", 5), ("stock", 15)])
def test_default_fees_are_identified_as_assumptions(market, fee):
    request = payload(market=market)
    del request["fee_bps"]
    data = client.post("/v1/backtests/compare", json=request).json()
    assert data["dataset"]["fee_bps"] == fee
    assert any("가정값" in limitation for limitation in data["limitations"])
