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
    if len(instrument.prices) < MA_PERIOD + 1:
        return False
    current = instrument.prices[0].close
    completed = [row.close for row in instrument.prices[1 : MA_PERIOD + 1]]
    return current > 0 and all(close > 0 for close in completed) and current >= sum(completed) / MA_PERIOD


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
