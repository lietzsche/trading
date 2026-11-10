import math
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Section 1: MA40 Calculation & Candle Windowing Rules
# ---------------------------------------------------------------------------

def calculate_ma(prices, period=40):
    """Reference implementation of MA40 logic matching calculation-service."""
    if len(prices) < period + 1:
        return False, None
    current = prices[0]
    completed = prices[1:period + 1]
    if current <= 0 or any(c <= 0 for c in completed):
        return False, None
    ma = sum(completed) / period
    is_above = current >= ma
    return is_above, ma


def test_ma40_forming_candle_strict_exclusion():
    """Today's forming candle (index 0) must NEVER be included in the MA calculation."""
    completed = [100.0] * 40
    expected_ma = 100.0

    # Changing index 0 to extreme values must not alter the MA threshold
    for c0 in [0.01, 50.0, 99.9999, 100.0, 100.0001, 1000.0, 1_000_000.0]:
        prices = [c0] + completed
        is_above, ma = calculate_ma(prices, 40)
        assert ma == pytest.approx(expected_ma, rel=1e-9), f"MA corrupted by index 0={c0}"
        if c0 >= 100.0:
            assert is_above is True
        else:
            assert is_above is False


def test_ma40_randomized_invariance_property():
    """Property test: For 50 randomized candle vectors, modifying index 0 has 0 effect on MA."""
    import random
    random.seed(12345)
    for _ in range(50):
        completed = [random.uniform(10.0, 50000.0) for _ in range(40)]
        expected_ma = sum(completed) / 40.0
        
        # Test just below, exact, and just above
        _, ma_below = calculate_ma([expected_ma - 1e-4] + completed, 40)
        _, ma_exact = calculate_ma([expected_ma] + completed, 40)
        _, ma_above = calculate_ma([expected_ma + 1e-4] + completed, 40)
        
        assert ma_below == pytest.approx(expected_ma, rel=1e-12)
        assert ma_exact == pytest.approx(expected_ma, rel=1e-12)
        assert ma_above == pytest.approx(expected_ma, rel=1e-12)


def test_ma40_exact_40_completed_candles_window():
    """Only indices 1..40 may be used. Trailing index 41+ must be completely ignored."""
    completed_40 = [100.0] * 40
    # Add a 41st completed candle with an astronomical value
    prices_with_huge_tail = [100.0] + completed_40 + [1e15]
    is_above, ma = calculate_ma(prices_with_huge_tail, 40)
    assert ma == 100.0
    assert is_above is True

    # Add a 41st candle with zero
    prices_with_zero_tail = [100.0] + completed_40 + [0.0]
    is_above, ma = calculate_ma(prices_with_zero_tail, 40)
    assert ma == 100.0
    assert is_above is True


def test_ma40_candle_count_boundaries():
    """Insufficient candles must be rejected safely without indexing errors."""
    for count in [0, 1, 2, 39, 40]:  # 40 candles = 1 forming + 39 completed -> insufficient!
        prices = [100.0] * count
        is_above, ma = calculate_ma(prices, 40)
        assert is_above is False
        assert ma is None

    # Exactly 41 candles (1 forming + 40 completed) -> valid!
    is_above, ma = calculate_ma([100.0] * 41, 40)
    assert is_above is True
    assert ma == 100.0


def test_ma40_exact_equality_and_epsilon():
    """Boundary test: current == MA40 must pass; current < MA40 by any epsilon must fail."""
    completed = [100.0] * 40
    
    # Exact equality
    is_above, _ = calculate_ma([100.0] + completed, 40)
    assert is_above is True

    # Epsilon below
    is_above, _ = calculate_ma([99.99999999999] + completed, 40)
    assert is_above is False

    # Epsilon above
    is_above, _ = calculate_ma([100.00000000001] + completed, 40)
    assert is_above is True


def test_ma40_all_completed_candles_must_be_positive():
    """If any completed candle has price <= 0, signal must evaluate False."""
    completed = [100.0] * 40
    completed[0] = 0.0  # first completed candle is 0
    is_above, ma = calculate_ma([100.0] + completed, 40)
    assert is_above is False

    completed2 = [100.0] * 40
    completed2[39] = 0.0  # 40th completed candle is 0
    is_above2, ma2 = calculate_ma([100.0] + completed2, 40)
    assert is_above2 is False


# ---------------------------------------------------------------------------
# Section 2: Numerical Extremes, Types & Precision
# ---------------------------------------------------------------------------

def test_extreme_price_scales():
    """Extreme price scales (Satoshi 1e-8 vs Trillion KRW 1e14) must compute accurately."""
    # Satoshi scale (e.g., low unit price tokens)
    satoshi_completed = [0.00000001] * 40
    is_above, ma = calculate_ma([0.00000001] + satoshi_completed, 40)
    assert is_above is True
    assert ma == pytest.approx(1e-8, rel=1e-9)

    is_below, _ = calculate_ma([0.000000009] + satoshi_completed, 40)
    assert is_below is False

    # Trillion scale
    trillion_completed = [1e14] * 40
    is_above_t, ma_t = calculate_ma([1e14] + trillion_completed, 40)
    assert is_above_t is True
    assert ma_t == pytest.approx(1e14, rel=1e-9)


def test_zero_current_price_rejection():
    """Current price 0.0 must evaluate to False even if completed candles are positive."""
    is_above, _ = calculate_ma([0.0] + [100.0] * 40, 40)
    assert is_above is False


# ---------------------------------------------------------------------------
# Section 3: Disparity Rate Ranking Stress & SQL Edge Cases
# ---------------------------------------------------------------------------

def disparity_formula(temp_price, setting_price):
    if setting_price is None or setting_price == 0:
        return None
    return (temp_price - setting_price) / setting_price


def test_disparity_rate_mathematical_ranking():
    """Disparity formula must correctly normalize percentage differences across price scales."""
    coins = [
        {"code": "KRW-SMALL", "temp": 1.5, "setting": 1.0},        # +50% disparity
        {"code": "KRW-MID",   "temp": 120.0, "setting": 100.0},     # +20% disparity
        {"code": "KRW-HUGE",  "temp": 105_000_000.0, "setting": 100_000_000.0},  # +5% disparity (KRW diff: 5M)
        {"code": "KRW-FLAT",  "temp": 500.0, "setting": 500.0},     # 0% disparity
    ]
    for c in coins:
        c["disparity"] = disparity_formula(c["temp"], c["setting"])

    ranked = sorted(coins, key=lambda c: c["disparity"], reverse=True)
    order = [c["code"] for c in ranked]
    assert order == ["KRW-SMALL", "KRW-MID", "KRW-HUGE", "KRW-FLAT"], (
        "Disparity rate must rank highest % gain first, not raw KRW difference!"
    )


def test_disparity_ranking_with_identical_ratios():
    """Tie-breaker check: coins with identical disparity sort by secondary key."""
    candidates = [
        {"id": 1, "code": "KRW-COIN1", "temp": 110.0, "setting": 100.0}, # +10%
        {"id": 2, "code": "KRW-COIN2", "temp": 22.0, "setting": 20.0},   # +10%
    ]
    for c in candidates:
        c["disparity"] = disparity_formula(c["temp"], c["setting"])

    # Sorting with secondary key id DESC
    ranked = sorted(candidates, key=lambda c: (c["disparity"], c["id"]), reverse=True)
    assert ranked[0]["id"] == 2
    assert ranked[1]["id"] == 1


def test_disparity_zero_and_null_setting_price_hazard():
    """Adversarial check: setting_price == 0 produces None (NULL).
    Without NULLS LAST, SQL ORDER BY ... DESC places NULL at the VERY TOP.
    This test verifies that Python/application logic protects against this hazard.
    """
    candidates = [
        {"id": 1, "code": "KRW-VALID", "temp": 120.0, "setting": 100.0}, # disparity = 0.2
        {"id": 2, "code": "KRW-ZERO",  "temp": 100.0, "setting": 0.0},   # disparity = None
    ]
    for c in candidates:
        c["disparity"] = disparity_formula(c["temp"], c["setting"])

    assert candidates[1]["disparity"] is None, "Division by zero setting_price must yield None"
    
    # In Python, sorting None with numbers raises TypeError or requires key helper
    # A safe ranking function must treat None as lowest priority (-infinity)
    def safe_sort_key(c):
        return c["disparity"] if c["disparity"] is not None else float("-inf")

    safe_ranked = sorted(candidates, key=safe_sort_key, reverse=True)
    assert safe_ranked[0]["code"] == "KRW-VALID"
    assert safe_ranked[1]["code"] == "KRW-ZERO"


# ---------------------------------------------------------------------------
# Section 4: Dust Balance (< 5,000 KRW) & Holdings Gate
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine():
    from app.trading import TradingEngine
    engine = TradingEngine(db=MagicMock(), calculation_url="http://calc:8000", enabled=False)
    codes = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
    engine._validated_upbit_codes = MagicMock(return_value=codes)
    engine.upbit_public = MagicMock(side_effect=lambda path, params=None: (
        [{"market": c} for c in codes] if "market" in path else
        [
            {"market": "KRW-BTC", "trade_price": 100_000_000},
            {"market": "KRW-ETH", "trade_price": 4_000_000},
            {"market": "KRW-XRP", "trade_price": 1_000},
        ]
    ))
    return engine


def test_dust_threshold_exact_boundaries(mock_engine):
    """4999.9999 KRW is dust; 5000.0 KRW is normal holding."""
    chance_loader = lambda m: {"market": {"ask": {"min_total": "5000"}}}

    # Case A: 4999.99 KRW (< 5000) -> dust
    accounts_sub = [
        {"currency": "KRW", "balance": "1000000", "locked": "0"},
        {"currency": "XRP", "balance": "4.99999", "locked": "0"},  # 4999.99 KRW
    ]
    res_sub = mock_engine.unsellable_balances(accounts_sub, chance_loader)
    assert res_sub.get("XRP") == "dust"

    # Case B: Exactly 5000.00 KRW (>= 5000) -> NOT dust
    accounts_exact = [
        {"currency": "KRW", "balance": "1000000", "locked": "0"},
        {"currency": "XRP", "balance": "5.0", "locked": "0"},  # 5000.0 KRW
    ]
    res_exact = mock_engine.unsellable_balances(accounts_exact, chance_loader)
    assert "XRP" not in res_exact


def test_locked_balance_dust_evaluation(mock_engine):
    """Locked balance must be included in valuation when evaluating dust threshold."""
    chance_loader = lambda m: {"market": {"ask": {"min_total": "5000"}}}
    # Available = 2.0 XRP (2,000 KRW), Locked = 3.5 XRP (3,500 KRW) -> Total = 5,500 KRW
    accounts = [
        {"currency": "KRW", "balance": "1000000", "locked": "0"},
        {"currency": "XRP", "balance": "2.0", "locked": "3.5"},
    ]
    res = mock_engine.unsellable_balances(accounts, chance_loader)
    assert "XRP" not in res, "Locked balance was ignored, causing false-positive dust classification!"


def test_unsupported_coin_excluded(mock_engine):
    """Coins without active Upbit KRW market must be flagged 'unsupported'."""
    chance_loader = lambda m: {"market": {"ask": {"min_total": "5000"}}}
    accounts = [
        {"currency": "KRW", "balance": "1000000", "locked": "0"},
        {"currency": "LUNA", "balance": "100.0", "locked": "0"},  # not in KRW markets
    ]
    res = mock_engine.unsellable_balances(accounts, chance_loader)
    assert res.get("LUNA") == "unsupported"


def test_unsellable_price_error_failsafe(mock_engine):
    """If ticker prices contain NaN or non-positive values, failsafe must return empty dict."""
    chance_loader = lambda m: {"market": {"ask": {"min_total": "5000"}}}
    # Inject NaN in prices
    mock_engine.upbit_public = MagicMock(side_effect=lambda path, params=None: (
        [{"market": "KRW-BTC"}] if "market" in path else
        [{"market": "KRW-BTC", "trade_price": float("nan")}]
    ))
    accounts = [
        {"currency": "KRW", "balance": "1000000", "locked": "0"},
        {"currency": "BTC", "balance": "0.00001", "locked": "0"},
    ]
    res = mock_engine.unsellable_balances(accounts, chance_loader)
    # Must fail-safe to empty dict so holdings gate stays closed
    assert res == {}


# ---------------------------------------------------------------------------
# Section 5: Full Auto-Order Decision & Order Execution Flow
# ---------------------------------------------------------------------------

def test_dust_balance_unblocks_auto_buy(mock_engine):
    """Dust crypto position must not block purchasing a top-ranked recommendation."""
    # Mock calc response: when only KRW is in balances, emit BUY action
    def mock_calc(endpoint, payload):
        recs = payload.get("recommended_markets", [])
        held = [f"KRW-{r['currency']}" for r in payload.get("balances", []) if r["currency"] != "KRW"]
        if held:
            return {"actions": [{"side": "SELL", "market": m} for m in held if m not in recs]}
        if recs:
            return {"actions": [{"side": "BUY", "market": recs[0]}]}
        return {"actions": []}

    mock_engine.calc = MagicMock(side_effect=mock_calc)
    mock_engine.reconcile_auto_orders = MagicMock(return_value={"blocked": 0})
    mock_engine.private_for_key = MagicMock(side_effect=lambda method, path, key, params=None: (
        [{"currency": "KRW", "balance": "1000000", "locked": "0"},
         {"currency": "BTC", "balance": "0.00001", "locked": "0"}] if path == "/v1/accounts" else
        {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}, "ask": {"min_total": "5000"}},
         "ask_account": {"balance": "0.00001"}} if path == "/v1/orders/chance" else
        {"uuid": "order-1", "state": "wait"}
    ))
    mock_engine.unsellable_balances = MagicMock(return_value={"BTC": "dust"})
    mock_engine.db.all = MagicMock(return_value=[])
    mock_engine.db.one = MagicMock(return_value={"id": 1})
    mock_engine._submit_auto_order = MagicMock(return_value={"uuid": "order-1", "state": "wait"})
    mock_engine.save_order = MagicMock()

    key = {"id": 1, "user_login_id": "test_user", "access_key": "k", "secret_key": "s"}
    mock_engine._auto_order_for_key(key, ["KRW-ETH", "KRW-BTC"])

    # Verify BUY was submitted for KRW-ETH
    mock_engine._submit_auto_order.assert_called_once()
    order_params = mock_engine._submit_auto_order.call_args[0][1]
    assert order_params["market"] == "KRW-ETH"
    assert order_params["side"] == "bid"
    assert order_params["ord_type"] == "price"
    # Verify fee deducted: 1,000,000 * (1 - 0.0005) = 999,500 KRW
    assert float(order_params["price"]) == pytest.approx(999500.0, rel=1e-5)
