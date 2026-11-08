from typing import Annotated, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field, FiniteFloat

MA_PERIOD = 40
NonNegativeFloat = Annotated[FiniteFloat, Field(ge=0)]


class Price(BaseModel):
    close: NonNegativeFloat
    high: NonNegativeFloat = 0
    low: NonNegativeFloat = 0
    open: NonNegativeFloat = 0
    diff: FiniteFloat = 0
    volume: NonNegativeFloat = 0


class Instrument(BaseModel):
    code: str
    name: str = ""
    prices: list[Price]
    ma_period: int = Field(default=MA_PERIOD, ge=2, le=199)


class SelectionRequest(BaseModel):
    instruments: list[Instrument]
    # Kept in the wire model during migration; MA40 itself is intentionally fixed.
    low_percentage: FiniteFloat = -1
    high_percentage: FiniteFloat = 1
    volume_check: bool = False
    amplitude_check: bool = False


class SelectionResponse(BaseModel):
    selected_codes: list[str]


class AccountBalance(BaseModel):
    currency: str


class AutoTradeRequest(BaseModel):
    recommended_markets: list[str]
    balances: list[AccountBalance]
    minimum_recommendations: int = Field(default=1, ge=1)


class TradeAction(BaseModel):
    side: Literal["BUY", "SELL"]
    market: str


class AutoTradeResponse(BaseModel):
    actions: list[TradeAction]


class BacktestCandle(BaseModel):
    date: str
    open: FiniteFloat = Field(gt=0)
    close: FiniteFloat = Field(gt=0)


class BacktestRequest(BaseModel):
    candles: list[BacktestCandle]
    ma_period: int = Field(default=MA_PERIOD, ge=2, le=199)
    initial_capital: FiniteFloat = Field(default=1_000_000, gt=0)
    fee_bps: FiniteFloat = Field(default=5, ge=0, le=1000)
    slippage_bps: FiniteFloat = Field(default=10, ge=0, le=1000)


app = FastAPI(title="Upbit MA40 Calculation Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "UP"}


@app.post("/v1/recommendations/select", response_model=SelectionResponse)
def select_recommendations(request: SelectionRequest) -> SelectionResponse:
    selected, seen = [], set()
    for instrument in request.instruments:
        if instrument.code not in seen and _above_ma40(instrument):
            selected.append(instrument.code)
            seen.add(instrument.code)
    return SelectionResponse(selected_codes=selected)


def _above_ma40(instrument: Instrument) -> bool:
    # Upbit returns newest first. prices[0] is today's still-forming candle.
    period = instrument.ma_period
    if len(instrument.prices) < period + 1:
        return False
    current = instrument.prices[0].close
    completed = [row.close for row in instrument.prices[1 : period + 1]]
    return current > 0 and all(close > 0 for close in completed) and current >= sum(completed) / period


@app.post("/v1/auto-trade/decide", response_model=AutoTradeResponse)
def decide_auto_trade(request: AutoTradeRequest) -> AutoTradeResponse:
    recommendations = list(dict.fromkeys(request.recommended_markets))
    held = list(dict.fromkeys(f"KRW-{row.currency}" for row in request.balances if row.currency != "KRW"))
    if held:
        return AutoTradeResponse(actions=[TradeAction(side="SELL", market=market)
                                          for market in held if market not in recommendations])
    if request.balances and recommendations:
        return AutoTradeResponse(actions=[TradeAction(side="BUY", market=market)
                                          for market in recommendations])
    return AutoTradeResponse(actions=[])


@app.post("/v1/backtests/ma40")
def backtest_ma40(request: BacktestRequest):
    rows = sorted(request.candles, key=lambda row: row.date)
    period = request.ma_period
    fee, slip = request.fee_bps / 10_000, request.slippage_bps / 10_000
    cash, quantity, trades, curve = float(request.initial_capital), 0.0, [], []
    entry_cost = None
    for index, row in enumerate(rows):
        if index:
            previous = rows[index - 1]
            history = rows[max(0, index - period - 1):index - 1]
            desired = len(history) == period and previous.close >= sum(item.close for item in history) / period
            if desired and quantity == 0:
                price = row.open * (1 + slip)
                quantity = cash * (1 - fee) / price
                entry_cost, cash = float(request.initial_capital) if not trades else cash, 0.0
                trades.append({"date": row.date, "side": "BUY", "price": price, "value": quantity * price})
            elif not desired and quantity > 0:
                price = row.open * (1 - slip)
                cash = quantity * price * (1 - fee)
                trades.append({"date": row.date, "side": "SELL", "price": price, "value": cash})
                quantity, entry_cost = 0.0, None
        equity = cash + quantity * row.close
        curve.append({"date": row.date, "equity": equity})
    if rows and quantity > 0:
        price = rows[-1].close * (1 - slip)
        cash = quantity * price * (1 - fee)
        trades.append({"date": rows[-1].date, "side": "SELL", "price": price, "value": cash, "forced": True})
        curve[-1]["equity"] = cash
    final = cash if rows else float(request.initial_capital)
    benchmark_pct = 0.0
    benchmark_start = period + 1
    if len(rows) > benchmark_start:
        benchmark_buy = rows[benchmark_start].open * (1 + slip)
        benchmark_quantity = request.initial_capital * (1 - fee) / benchmark_buy
        benchmark_final = benchmark_quantity * rows[-1].close * (1 - slip) * (1 - fee)
        benchmark_pct = (benchmark_final / request.initial_capital - 1) * 100
    peak, max_drawdown = 0.0, 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        if peak:
            max_drawdown = max(max_drawdown, (peak - point["equity"]) * 100 / peak)
    return {"ma_period": period, "initial_capital": request.initial_capital, "final_equity": final,
            "return_pct": (final / request.initial_capital - 1) * 100, "benchmark_return_pct": benchmark_pct,
            "excess_return_pct": (final / request.initial_capital - 1) * 100 - benchmark_pct,
            "max_drawdown_pct": max_drawdown, "trade_count": len([t for t in trades if t["side"] == "SELL"]),
            "trades": trades, "curve": curve}
