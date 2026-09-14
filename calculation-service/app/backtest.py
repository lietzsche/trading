"""Bounded, read-only, close-signal / next-open historical comparisons.

An equal-weight collection of independent single-instrument experiments, not
a reproduction of the account-level automatic order engine.
"""

import hashlib
import json
import math
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, FiniteFloat, model_validator


MIN_EVALUATION_DAYS = 30
MAX_SEARCH_COMBINATIONS = 40
PositivePrice = Annotated[FiniteFloat, Field(ge=1e-12, le=1e15)]
CostBps = Annotated[FiniteFloat, Field(ge=0, le=100)]
router = APIRouter()


class HistoricalPrice(BaseModel):
    date: date
    open: PositivePrice
    high: PositivePrice
    low: PositivePrice
    close: PositivePrice
    volume: Annotated[FiniteFloat, Field(ge=0, le=1e30)]

    @model_validator(mode="after")
    def coherent_prices(self):
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("일봉의 고가·저가가 시가·종가 범위를 포함해야 합니다.")
        return self


class HistoricalInstrument(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(default="", max_length=100)
    prices: list[HistoricalPrice] = Field(min_length=3, max_length=200)

    @model_validator(mode="after")
    def unique_dates(self):
        dates = [price.date for price in self.prices]
        if len(set(dates)) != len(dates):
            raise ValueError("같은 종목에 날짜가 중복된 일봉이 있습니다.")
        self.prices.sort(key=lambda price: price.date)
        return self


class Candidate(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=100)
    expected_high_percentage: int = Field(ge=1, le=1000)
    expected_low_percentage: int = Field(ge=-99, le=1000)
    highest_price_reference_days: int = Field(ge=3, le=200)
    volume_check: bool

    @model_validator(mode="after")
    def correct_setting_range(self):
        if self.expected_low_percentage >= self.expected_high_percentage:
            raise ValueError("하한 비율은 목표 상승률보다 작아야 합니다.")
        return self


class ComparisonRequest(BaseModel):
    market: Literal["stock", "upbit"]
    instruments: list[HistoricalInstrument] = Field(min_length=1, max_length=5)
    candidates: list[Candidate] = Field(min_length=1, max_length=4)
    fee_bps: CostBps | None = None
    slippage_bps: CostBps = 10

    @model_validator(mode="after")
    def unique_items(self):
        codes = [instrument.code for instrument in self.instruments]
        if len(codes) != len(set(codes)):
            raise ValueError("비교 종목은 중복될 수 없습니다.")
        ids = [candidate.id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("설정 후보 식별자는 중복될 수 없습니다.")
        return self


class SearchAxis(BaseModel):
    values: list[int] = Field(min_length=1, max_length=3)


class SearchSpace(BaseModel):
    expected_high_percentage: SearchAxis
    expected_low_percentage: SearchAxis
    highest_price_reference_days: SearchAxis
    volume_check: list[bool] = Field(default=[False, True], min_length=1, max_length=2)


class SearchRequest(BaseModel):
    market: Literal["stock", "upbit"]
    instruments: list[HistoricalInstrument] = Field(min_length=1, max_length=5)
    search_space: SearchSpace
    fee_bps: CostBps | None = None
    slippage_bps: CostBps = 10
    minimum_validation_trades: int = Field(default=5, ge=1, le=100)
    top_n: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def unique_instruments_and_bounded_grid(self):
        codes = [instrument.code for instrument in self.instruments]
        if len(codes) != len(set(codes)):
            raise ValueError("비교 종목은 중복될 수 없습니다.")
        space = self.search_space
        size = (len(space.expected_high_percentage.values) * len(space.expected_low_percentage.values)
                * len(space.highest_price_reference_days.values) * len(space.volume_check))
        if size > MAX_SEARCH_COMBINATIONS:
            raise ValueError(f"탐색 조합이 최대 {MAX_SEARCH_COMBINATIONS}개를 초과합니다. 각 값의 후보 개수를 줄여 주세요.")
        return self


def _metrics(curve, buys, sells, open_positions):
    peak, drawdown = 1.0, 0.0
    for equity in curve.values():
        if not math.isfinite(equity) or equity < 0:
            raise HTTPException(422, "백테스트 계산 결과가 안전한 수치 범위를 벗어났습니다.")
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    final = next(reversed(curve.values())) if curve else 1.0
    return {
        "return_pct": round((final - 1) * 100, 6),
        "max_drawdown_pct": round(drawdown * 100, 6),
        "trades": sells, "days": len(curve),
        "buys": buys, "sells": sells, "open_positions": open_positions,
    }


def _simulate_segment(instrument, candidate, market, start, end, fee, slippage):
    # Lazy imports avoid a circular dependency during main.app initialization.
    from .main import Instrument, Position, Price, SelectionRequest, UpdateRequest
    from .main import _is_recommended, _update_position

    rows = instrument.prices
    price_models = [Price(**row.model_dump(exclude={"date"})) for row in rows]
    lookback = candidate.highest_price_reference_days
    selection = SelectionRequest(
        instruments=[], low_percentage=candidate.expected_low_percentage,
        high_percentage=candidate.expected_high_percentage,
        volume_check=candidate.volume_check, amplitude_check=market == "stock",
    )
    update = UpdateRequest(
        positions=[], high_multiplier=1 + candidate.expected_high_percentage / 100,
        low_multiplier=1 + candidate.expected_low_percentage / 100,
    )

    def entry_signal(index):
        if index < lookback - 1 or rows[index].volume == 0:
            return None
        history = list(reversed(price_models[index - lookback + 1:index + 1]))
        if not _is_recommended(Instrument(code=instrument.code, prices=history), selection):
            return None
        close = rows[index].close
        return Position(
            code=instrument.code, prices=[],
            expected_selling_price=close * update.high_multiplier,
            minimum_selling_price=close * update.low_multiplier,
            temp_price=close, setting_price=close,
        )

    indices = [index for index, row in enumerate(rows) if start <= row.date <= end]
    cash, quantity = 1.0, 0.0
    buys = sells = 0
    curve = {}
    position = None
    # A fully observed warmup close may signal an entry at the first evaluation open.
    pending_buy = entry_signal(indices[0] - 1) if indices else None
    pending_sell = False
    for index in indices:
        row = rows[index]
        if row.volume > 0:
            if pending_sell and position is not None:
                cash = quantity * row.open * (1 - slippage) * (1 - fee)
                quantity, position, pending_sell = 0.0, None, False
                sells += 1
            elif pending_buy is not None and position is None:
                quantity = cash / (row.open * (1 + slippage) * (1 + fee))
                cash, position, pending_buy = 0.0, pending_buy, None
                buys += 1

            if position is not None:
                position.prices = [price_models[index]]
                updated = _update_position(position, update)
                pending_sell = updated.action == "DELETE"
                position.expected_selling_price = updated.expected_selling_price
                position.minimum_selling_price = updated.minimum_selling_price
                position.temp_price = updated.temp_price
                position.setting_price = updated.setting_price
                position.renewal_count = updated.renewal_count
            elif pending_buy is None:
                pending_buy = entry_signal(index)
        curve[row.date] = cash + quantity * row.close

    return {"curve": curve, "buys": buys, "sells": sells,
            "open_positions": int(position is not None)}


def _portfolio_metrics(simulations):
    # Equal initial allocations; no fictitious daily rebalance or averaged MDD.
    dates = sorted({day for simulation in simulations for day in simulation["curve"]})
    last_values = [1.0] * len(simulations)
    portfolio_curve = {}
    for day in dates:
        for index, simulation in enumerate(simulations):
            last_values[index] = simulation["curve"].get(day, last_values[index])
        portfolio_curve[day] = sum(last_values) / len(last_values)
    return _metrics(portfolio_curve,
                    sum(item["buys"] for item in simulations),
                    sum(item["sells"] for item in simulations),
                    sum(item["open_positions"] for item in simulations))


@router.post("/v1/backtests/compare")
def compare_backtests(request: ComparisonRequest):
    common_dates = sorted(set.intersection(*(
        {row.date for row in instrument.prices} for instrument in request.instruments
    )))
    warmup = max(candidate.highest_price_reference_days for candidate in request.candidates)
    if len(common_dates) < warmup + MIN_EVALUATION_DAYS:
        raise HTTPException(422, detail=(
            f"백테스트 자료가 부족합니다. 모든 종목에 공통으로 준비 기간 {warmup}봉과 "
            f"평가 기간 {MIN_EVALUATION_DAYS}봉 이상이 필요하지만 공통 일봉은 {len(common_dates)}개입니다. "
            "최대 200봉을 조회하므로 기준 기간이 긴 설정은 현재 검증할 수 없습니다."
        ))
    evaluation = common_dates[warmup:]
    split = int(len(evaluation) * 0.7)
    train_start, train_end = evaluation[0], evaluation[split - 1]
    validation_start, validation_end = evaluation[split], evaluation[-1]
    fee_bps = request.fee_bps if request.fee_bps is not None else (5 if request.market == "upbit" else 15)
    fee, slippage = fee_bps / 10_000, request.slippage_bps / 10_000
    warnings = []
    if len(evaluation) - split < 30:
        warnings.append("검증 기간이 30봉 미만으로 짧습니다. 결과 변동성이 크며 설정의 안정성을 판단하기 어렵습니다.")
    for instrument in request.instruments:
        rows = instrument.prices
        if len(rows) != len(common_dates):
            warnings.append(f"{instrument.code}: 종목별 일봉 날짜가 달라 공통 날짜로 비교 구간을 정했습니다. 개별 과거 봉은 그대로 사용합니다.")
        gap_limit = 1 if request.market == "upbit" else 7
        if any((right.date - left.date).days > gap_limit for left, right in zip(rows, rows[1:])):
            warnings.append(f"{instrument.code}: 일봉 사이 공백이 있습니다. 미거래·휴장·자료 누락을 구분할 수 없으며 임의로 가격을 채우지 않았습니다.")
        if any(row.volume == 0 for row in rows):
            warnings.append(f"{instrument.code}: 거래량 0인 봉에서는 주문을 체결하지 않고 다음 거래 가능한 봉까지 기다립니다.")

    results = []
    for candidate in request.candidates:
        trains, validations, individual = [], [], []
        for instrument in request.instruments:
            train = _simulate_segment(instrument, candidate, request.market, train_start, train_end, fee, slippage)
            validation = _simulate_segment(instrument, candidate, request.market, validation_start, validation_end, fee, slippage)
            trains.append(train)
            validations.append(validation)
            individual.append({"code": instrument.code, "name": instrument.name,
                               "train": _metrics(**train), "validation": _metrics(**validation)})
        train_metrics, validation_metrics = _portfolio_metrics(trains), _portfolio_metrics(validations)
        if validation_metrics["trades"] == 0:
            warnings.append(f"{candidate.label}: 검증 구간에서 청산 완료 거래가 없어 수익성을 판단하기 어렵습니다.")
        results.append({"id": candidate.id, "label": candidate.label,
                        "settings": candidate.model_dump(exclude={"id", "label"}),
                        "train": train_metrics, "validation": validation_metrics,
                        "per_instrument": individual})

    canonical = json.dumps([instrument.model_dump(mode="json") for instrument in request.instruments],
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "candidates": results,
        "dataset": {
            "market": request.market,
            "data_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "warmup_days": warmup,
            "comparison_start": train_start.isoformat(), "comparison_end": validation_end.isoformat(),
            "train_start": train_start.isoformat(), "train_end": train_end.isoformat(),
            "validation_start": validation_start.isoformat(), "validation_end": validation_end.isoformat(),
            "train_days": split, "validation_days": len(evaluation) - split,
            "fee_bps": fee_bps, "slippage_bps": request.slippage_bps,
            "instruments": [{"code": item.code, "name": item.name, "bars": len(item.prices),
                             "start": item.prices[0].date.isoformat(), "end": item.prices[-1].date.isoformat()}
                            for item in request.instruments],
        },
        "warnings": warnings,
        "limitations": [
            "과거 일봉의 종가로 신호를 계산하고 다음 거래 가능한 봉의 시가로만 체결하는 가상 실험입니다. 장중 고가·저가 도달 순서를 추정하지 않습니다.",
            "종목별 동일 초기 비중·분리 자금으로 계산하며, 실제 계좌 자동매매의 최소 추천 수·매수 순서·정수 주식 수량·최소 주문액·호가 단위는 재현하지 않습니다.",
            "전체 후보가 같은 시세·비교 기간을 사용합니다. 공통 준비 기간 이후 앞 70%는 훈련, 뒤 30%는 검증이며 검증 시작 시 현금과 보유 상태를 초기화합니다.",
            "검증 이전 과거 봉은 지표 준비에만 사용합니다. AI가 이미 시세를 본 뒤 제안한 후보이므로 검증 구간은 완전히 보지 않은 독립 표본이 아닐 수 있습니다.",
            "수수료와 슬리피지는 매수·매도 각각 적용하는 가정값입니다. 실제 세금·수수료 할인·시장 충격·배당·분할·상장폐지·생존 편향은 반영되지 않습니다.",
            "미청산 보유분은 마지막 종가로 평가하며 아직 발생하지 않은 매도 비용은 차감하지 않습니다. 거래 횟수는 청산 완료 횟수입니다.",
            "짧고 제한된 종목 표본의 과거 결과이며 미래 수익을 예측하거나 보장하지 않습니다.",
        ],
    }


@router.post("/v1/backtests/search")
def search_backtests(request: SearchRequest):
    """Grid-search a bounded set of setting combinations via `compare_backtests`
    and rank them by validation-segment return. Read-only research: this never
    saves or applies a setting, and callers must not treat "best in this
    window" as a promise of future performance (classic overfitting risk)."""
    space = request.search_space
    combinations = [
        {"expected_high_percentage": high, "expected_low_percentage": low,
         "highest_price_reference_days": days, "volume_check": volume_check}
        for high in space.expected_high_percentage.values
        for low in space.expected_low_percentage.values
        for days in space.highest_price_reference_days.values
        for volume_check in space.volume_check
        if low < high
    ]
    if not combinations:
        raise HTTPException(422, "유효한 조합이 없습니다. 하한 비율은 상한보다 작아야 합니다.")
    candidates = [Candidate(id=f"search-{index}", label=f"탐색 조합 {index + 1}", **combo)
                  for index, combo in enumerate(combinations)]
    comparison = compare_backtests(ComparisonRequest(
        market=request.market, instruments=request.instruments, candidates=candidates,
        fee_bps=request.fee_bps, slippage_bps=request.slippage_bps))
    eligible = [item for item in comparison["candidates"]
                if item["validation"]["trades"] >= request.minimum_validation_trades]
    ranked = sorted(eligible, key=lambda item: item["validation"]["return_pct"], reverse=True)
    top = [{key: value for key, value in item.items() if key != "per_instrument"} for item in ranked[:request.top_n]]
    warnings = list(comparison["warnings"])
    if not eligible:
        warnings.append(f"검증 구간 청산 거래 {request.minimum_validation_trades}건 이상인 조합이 없어 판별 가능한 결과가 없습니다.")
    return {
        "top_candidates": top, "combinations_evaluated": len(combinations), "combinations_eligible": len(eligible),
        "minimum_validation_trades": request.minimum_validation_trades, "dataset": comparison["dataset"],
        "warnings": warnings,
        "limitations": comparison["limitations"] + [
            "그리드 탐색 결과는 같은 과거 표본에 대한 과최적화(overfitting) 위험이 있습니다. "
            "검증 구간 성과가 가장 높다는 것이 미래 성과를 보장하지 않으며, 이 결과만으로는 어떤 설정도 저장·적용되지 않습니다.",
        ],
    }
