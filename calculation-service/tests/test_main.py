import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def prices():
    return [
        {"close": 119, "high": 120, "low": 110, "volume": 100},
        {"close": 108, "high": 110, "low": 100, "volume": 90},
        {"close": 98, "high": 100, "low": 90, "volume": 80},
        {"close": 100, "high": 105, "low": 95, "volume": 70},
    ]


def test_health():
    assert client.get("/health").json() == {"status": "UP"}


def test_selects_matching_instrument_once():
    response = client.post(
        "/v1/recommendations/select",
        json={
            "instruments": [
                {"code": "KRW-TEST", "prices": prices()},
                {"code": "KRW-TEST", "prices": prices()},
            ],
            "low_percentage": -5,
            "high_percentage": 10,
            "volume_check": False,
            "amplitude_check": True,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"selected_codes": ["KRW-TEST"]}


def test_updates_target_and_stop_prices():
    response = client.post(
        "/v1/recommendations/update",
        json={
            "positions": [
                {
                    "code": "KRW-TEST",
                    "prices": [{"close": 121, "high": 122, "low": 115, "volume": 1}],
                    "expected_selling_price": 120,
                    "minimum_selling_price": 90,
                    "temp_price": 100,
                    "setting_price": 100,
                    "renewal_count": 0,
                }
            ],
            "high_multiplier": 1.1,
            "low_multiplier": 0.9,
        },
    )
    result = response.json()["positions"][0]
    assert result["action"] == "KEEP"
    assert result["expected_selling_price"] == 132
    assert result["minimum_selling_price"] == 108
    assert result["renewal_count"] == 1


def test_update_keeps_position_when_price_is_missing():
    response = client.post(
        "/v1/recommendations/update",
        json={
            "positions": [
                {
                    "code": "KRW-TEST",
                    "prices": [],
                    "expected_selling_price": 120,
                    "minimum_selling_price": 90,
                    "temp_price": 100,
                    "setting_price": 100,
                }
            ],
            "high_multiplier": 1.1,
            "low_multiplier": 0.9,
        },
    )
    assert response.json()["positions"][0]["action"] == "KEEP"


def test_update_deletes_position_at_stop_price():
    response = client.post(
        "/v1/recommendations/update",
        json={
            "positions": [
                {
                    "code": "KRW-TEST",
                    "prices": [{"close": 89, "high": 95, "low": 85, "volume": 1}],
                    "expected_selling_price": 120,
                    "minimum_selling_price": 90,
                    "temp_price": 100,
                    "setting_price": 100,
                }
            ],
            "high_multiplier": 1.1,
            "low_multiplier": 0.9,
        },
    )
    assert response.json()["positions"][0]["action"] == "DELETE"


def test_auto_trade_sells_unrecommended_holding():
    response = client.post(
        "/v1/auto-trade/decide",
        json={
            "recommended_markets": ["KRW-BTC", "KRW-ETH", "KRW-XRP"],
            "balances": [{"currency": "ADA"}],
        },
    )
    assert response.json() == {"actions": [{"side": "SELL", "market": "KRW-ADA"}]}


def test_auto_trade_buys_only_with_at_least_three_recommendations():
    payload = {
        "recommended_markets": ["KRW-BTC", "KRW-ETH"],
        "balances": [{"currency": "KRW"}],
    }
    assert client.post("/v1/auto-trade/decide", json=payload).json() == {"actions": []}
    payload["recommended_markets"].append("KRW-XRP")
    assert len(client.post("/v1/auto-trade/decide", json=payload).json()["actions"]) == 3


def update_payload():
    return {
        "positions": [{
            "code": "KRW-TEST",
            "prices": [{"close": 121, "high": 122, "low": 115, "volume": 1}],
            "expected_selling_price": 120,
            "minimum_selling_price": 90,
            "temp_price": 100,
            "setting_price": 100,
            "renewal_count": 2,
        }],
        "high_multiplier": 1.1,
        "low_multiplier": 0.9,
    }


@pytest.mark.parametrize("multiplier", [0, -1, 0.99, 1, "NaN", "Infinity"])
def test_update_rejects_non_increasing_or_non_finite_high_multiplier(multiplier):
    payload = update_payload()
    payload["high_multiplier"] = multiplier
    assert client.post("/v1/recommendations/update", json=payload).status_code == 422


@pytest.mark.parametrize("multiplier", [0, -1, 1.1, 1.2, "NaN", "Infinity"])
def test_update_rejects_invalid_low_multiplier(multiplier):
    payload = update_payload()
    payload["low_multiplier"] = multiplier
    assert client.post("/v1/recommendations/update", json=payload).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("close", -1), ("high", -1), ("low", -1), ("open", -1), ("volume", -1),
    ("close", "NaN"), ("high", "Infinity"), ("diff", "-Infinity"),
])
def test_update_rejects_invalid_quotes(field, value):
    payload = update_payload()
    payload["positions"][0]["prices"][0][field] = value
    assert client.post("/v1/recommendations/update", json=payload).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("expected_selling_price", -1), ("minimum_selling_price", "NaN"),
    ("temp_price", "Infinity"), ("setting_price", -1), ("renewal_count", -1),
])
def test_update_rejects_invalid_position_values(field, value):
    payload = update_payload()
    payload["positions"][0][field] = value
    assert client.post("/v1/recommendations/update", json=payload).status_code == 422


def test_update_keeps_position_when_current_quote_is_zero():
    payload = update_payload()
    payload["positions"][0]["prices"][0]["close"] = 0
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 200
    position = response.json()["positions"][0]
    assert position["action"] == "KEEP"
    assert position["temp_price"] == 100
    assert position["expected_selling_price"] == 120
    assert position["minimum_selling_price"] == 90
    assert position["renewal_count"] == 2
    assert position["pricing_reference_date"] is None


def test_update_renews_at_exact_target_and_preserves_existing_level():
    payload = update_payload()
    payload["positions"][0]["prices"][0]["close"] = 120
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 200
    position = response.json()["positions"][0]
    assert position["expected_selling_price"] == 132
    assert position["minimum_selling_price"] == 108
    assert position["renewal_count"] == 3


def test_update_advances_multiple_levels_using_the_existing_formula():
    payload = update_payload()
    payload["positions"][0]["prices"][0]["close"] = 150
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 200
    position = response.json()["positions"][0]
    assert position["expected_selling_price"] == pytest.approx(159.72)
    assert position["minimum_selling_price"] == pytest.approx(130.68)
    assert position["renewal_count"] == 5
    assert position["setting_price"] == 150


def test_update_skips_latest_non_trading_candle():
    payload = update_payload()
    payload["positions"][0]["prices"].insert(0, {"close": 0, "high": 0, "low": 0, "volume": 0})
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 200
    assert response.json()["positions"][0]["expected_selling_price"] == 132


def test_update_rejects_overflow_without_returning_partial_results():
    payload = update_payload()
    position = dict(payload["positions"][0])
    position.update({
        "code": "KRW-OVERFLOW",
        "expected_selling_price": 1e308,
        "prices": [{"close": 1.7e308, "high": 1.7e308, "low": 1e308, "volume": 1}],
    })
    payload["positions"].append(position)
    payload["high_multiplier"] = 11
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 422
    assert "numeric range" in response.json()["detail"]
    assert "positions" not in response.json()


def test_update_rejects_impractically_small_step_without_hanging():
    payload = update_payload()
    payload["high_multiplier"] = 1.0000000000000002
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 422
    assert "iteration limit" in response.json()["detail"]


def test_update_rejects_step_lost_to_float_rounding():
    payload = update_payload()
    payload["high_multiplier"] = 1.0000000000000002
    payload["positions"][0]["expected_selling_price"] = 5e-324
    response = client.post("/v1/recommendations/update", json=payload)
    assert response.status_code == 422
    assert "numeric range" in response.json()["detail"]


@pytest.mark.parametrize("low,high", [(-100, 10), (-5, 0), (10, 10), (11, 10), ("NaN", 10), (-5, "Infinity")])
def test_selection_rejects_invalid_percentage_ranges(low, high):
    response = client.post("/v1/recommendations/select", json={
        "instruments": [], "low_percentage": low, "high_percentage": high,
    })
    assert response.status_code == 422


def test_selection_does_not_recommend_a_zero_quote_for_a_low_price_asset():
    response = client.post("/v1/recommendations/select", json={
        "instruments": [{"code": "KRW-ZERO", "prices": [
            {"close": 0, "high": 0.4, "low": 0.3, "volume": 1},
            {"close": 0.2, "high": 0.3, "low": 0.2, "volume": 1},
            {"close": 0.1, "high": 0.2, "low": 0.1, "volume": 1},
        ]}],
        "low_percentage": -5,
        "high_percentage": 10,
        "amplitude_check": False,
    })
    assert response.status_code == 200
    assert response.json() == {"selected_codes": []}


def test_auto_trade_does_not_duplicate_sell_instructions():
    response = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": ["KRW-BTC", "KRW-ETH", "KRW-XRP"],
        "balances": [{"currency": "ADA"}, {"currency": "ADA"}],
    })
    assert response.status_code == 200
    assert response.json() == {"actions": [{"side": "SELL", "market": "KRW-ADA"}]}


def test_auto_trade_rejects_zero_minimum_recommendations():
    response = client.post("/v1/auto-trade/decide", json={
        "recommended_markets": ["KRW-BTC"],
        "balances": [{"currency": "KRW"}],
        "minimum_recommendations": 0,
    })
    assert response.status_code == 422
