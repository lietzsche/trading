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
