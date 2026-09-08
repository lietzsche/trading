from datetime import datetime
from typing import Literal

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field


class Price(BaseModel):
    close: float
    high: float
    low: float
    open: float = 0
    diff: float = 0
    volume: float


class Instrument(BaseModel):
    code: str
    name: str = ""
    prices: list[Price]


class SelectionRequest(BaseModel):
    instruments: list[Instrument]
    low_percentage: float
    high_percentage: float
    volume_check: bool = False
    amplitude_check: bool = True


class SelectionResponse(BaseModel):
    selected_codes: list[str]


class Position(Instrument):
    expected_selling_price: float
    minimum_selling_price: float
    temp_price: float
    setting_price: float
    renewal_count: int = 0


class UpdateRequest(BaseModel):
    positions: list[Position]
    high_multiplier: float = Field(gt=0)
    low_multiplier: float = Field(gt=0)


class PositionResult(BaseModel):
    code: str
    action: Literal["KEEP", "DELETE"]
    expected_selling_price: float
    minimum_selling_price: float
    temp_price: float
    setting_price: float
    renewal_count: int
    pricing_reference_date: datetime | None = None


class UpdateResponse(BaseModel):
    positions: list[PositionResult]


class AccountBalance(BaseModel):
    currency: str


class AutoTradeRequest(BaseModel):
    recommended_markets: list[str]
    balances: list[AccountBalance]
    minimum_recommendations: int = 3


class TradeAction(BaseModel):
    side: Literal["BUY", "SELL"]
    market: str


class AutoTradeResponse(BaseModel):
    actions: list[TradeAction]


app = FastAPI(title="Trading Calculation Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "UP"}


@app.post("/v1/recommendations/select", response_model=SelectionResponse)
def select_recommendations(request: SelectionRequest) -> SelectionResponse:
    selected: list[str] = []
    seen: set[str] = set()
    for instrument in request.instruments:
        if instrument.code in seen or not _is_recommended(instrument, request):
            continue
        seen.add(instrument.code)
        selected.append(instrument.code)
    return SelectionResponse(selected_codes=selected)


def _is_recommended(instrument: Instrument, request: SelectionRequest) -> bool:
    if len(instrument.prices) < 3:
        return False
    frame = pd.DataFrame([price.model_dump() for price in instrument.prices])
    last = 1 if frame.iloc[0].volume == 0 else 0
    if len(frame) < last + 3:
        return False
    recent = frame.iloc[last : last + 3]
    if request.volume_check and frame.iloc[0].volume == recent.volume.max():
        return False
    if not (recent.high.iloc[0] > recent.high.iloc[1] > recent.high.iloc[2]):
        return False
    if not (recent.low.iloc[0] > recent.low.iloc[1] > recent.low.iloc[2]):
        return False
    if recent.close.iloc[0] < round(recent.high.iloc[0] * (1 + request.low_percentage / 100)):
        return False
    if recent.high.iloc[0] != frame.high.max():
        return False
    if not request.amplitude_check:
        return True
    amplitude = frame.head(20).high
    if amplitude.empty or amplitude.min() == 0:
        return False
    amplitude_percentage = (amplitude.max() - amplitude.min()) / amplitude.min() * 100
    return request.high_percentage <= amplitude_percentage <= request.high_percentage * 3


@app.post("/v1/recommendations/update", response_model=UpdateResponse)
def update_recommendations(request: UpdateRequest) -> UpdateResponse:
    return UpdateResponse(
        positions=[_update_position(position, request) for position in request.positions]
    )


def _update_position(position: Position, request: UpdateRequest) -> PositionResult:
    if not position.prices:
        return _position_result(position, "KEEP")
    last = 1 if position.prices[0].volume == 0 else 0
    if last >= len(position.prices):
        return _position_result(position, "KEEP")
    close = position.prices[last].close
    expected = position.expected_selling_price
    minimum = position.minimum_selling_price
    setting = position.setting_price
    renewal = position.renewal_count
    changed_at = None
    while close != 0 and expected != 0 and close >= expected:
        minimum = expected * request.low_multiplier
        expected *= request.high_multiplier
        setting = close
        renewal += 1
        changed_at = datetime.now()
    action: Literal["KEEP", "DELETE"] = "DELETE" if close <= minimum else "KEEP"
    return PositionResult(
        code=position.code,
        action=action,
        expected_selling_price=expected,
        minimum_selling_price=minimum,
        temp_price=close,
        setting_price=setting,
        renewal_count=renewal,
        pricing_reference_date=changed_at,
    )


def _position_result(position: Position, action: Literal["KEEP", "DELETE"]) -> PositionResult:
    return PositionResult(
        code=position.code,
        action=action,
        expected_selling_price=position.expected_selling_price,
        minimum_selling_price=position.minimum_selling_price,
        temp_price=position.temp_price,
        setting_price=position.setting_price,
        renewal_count=position.renewal_count,
    )


@app.post("/v1/auto-trade/decide", response_model=AutoTradeResponse)
def decide_auto_trade(request: AutoTradeRequest) -> AutoTradeResponse:
    recommendations = list(dict.fromkeys(request.recommended_markets))
    held_markets = [f"KRW-{item.currency}" for item in request.balances if item.currency != "KRW"]
    if held_markets:
        actions = [
            TradeAction(side="SELL", market=market)
            for market in held_markets
            if len(recommendations) < request.minimum_recommendations or market not in recommendations
        ]
    elif request.balances and len(recommendations) >= request.minimum_recommendations:
        actions = [TradeAction(side="BUY", market=market) for market in recommendations]
    else:
        actions = []
    return AutoTradeResponse(actions=actions)
