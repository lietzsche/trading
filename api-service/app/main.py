import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Literal

import bcrypt
import httpx
import psycopg
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from psycopg.rows import dict_row
from app.trading import TradingEngine, sort_recommendation_rows
from app.us_market import is_us_symbol
from app.auth_security import authenticate
from app.credentials import encrypt_upbit, migrate_upbit_credentials
from ipaddress import ip_address


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bion_user@postgres:5432/postgres")
CALCULATION_SERVICE_URL = os.environ.get("CALCULATION_SERVICE_URL", "http://calculation-service:8000")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
SESSION_MAX_AGE = 60 * 60 * 12
STARTED_AT = time.monotonic()
TRADING_ENABLED = os.environ.get("TRADING_EXECUTION_ENABLED", "false").lower() == "true"
SIGNUP_ENABLED = os.environ.get('SIGNUP_ENABLED','true').lower() == 'true'
SINGLE_USER_ONLY = os.environ.get('SINGLE_USER_ONLY','false').lower() == 'true'
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b'not-a-real-account-password',bcrypt.gensalt()).decode()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class LoginRequest(BaseModel):
    login_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserUpdate(BaseModel):
    user_role: Literal["USER", "ADMIN", "MASTER"]
    deleted: bool = False


class AutoUpdate(BaseModel):
    auto_on: bool


CandleIntervalType = Literal["15m", "30m", "60m", "240m", "days", "weeks"]


class BacktestRun(BaseModel):
    market: str = Field(default="KRW-BTC", pattern=r"^KRW-[A-Z0-9]{1,20}$")
    candle_interval: CandleIntervalType = Field(default="days")
    days: int = Field(default=180, ge=60, le=200)
    ma_period: int = Field(default=40, ge=2, le=199)
    initial_capital: float = Field(default=1_000_000, gt=0, le=1_000_000_000_000)
    fee_bps: float = Field(default=5, ge=0, le=1000)
    slippage_bps: float = Field(default=10, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_backtest_window(self):
        if self.days < self.ma_period + 2:
            raise ValueError("테스트 기간은 기준 봉 수보다 최소 2일 길어야 합니다.")
        return self


class MarketStrategyUpdate(BaseModel):
    market: str = Field(default="__GLOBAL__", pattern=r"^(__GLOBAL__|KRW-[A-Z0-9]{1,20})$")
    candle_interval: CandleIntervalType = Field(default="days")
    ma_period: int = Field(default=40, ge=2, le=199)
    days: int = Field(default=180, ge=60, le=200)
    initial_capital: float = Field(default=1_000_000, gt=0, le=1_000_000_000_000)
    fee_bps: float = Field(default=5, ge=0, le=1000)
    slippage_bps: float = Field(default=10, ge=0, le=1000)
    auto_trade: bool | None = None

    @model_validator(mode="after")
    def validate_strategy_window(self):
        if self.days < self.ma_period + 2:
            raise ValueError("백테스트 기간은 기준 봉 수보다 최소 2일 길어야 합니다.")
        return self


class MarketAutoTradeUpdate(BaseModel):
    market: str | None = Field(default=None, pattern=r"^KRW-[A-Z0-9]{1,20}$")
    markets: list[str] | None = None
    auto_trade: bool

    @model_validator(mode="after")
    def validate_targets(self):
        targets: list[str] = []
        if self.market:
            targets.append(self.market)
        if self.markets:
            for item in self.markets:
                if not isinstance(item, str) or not re.fullmatch(r"KRW-[A-Z0-9]{1,20}", item):
                    raise ValueError("올바른 KRW 마켓을 입력해 주세요.")
                if item not in targets:
                    targets.append(item)
        if not targets:
            raise ValueError("대상 마켓을 1개 이상 지정해 주세요.")
        self.markets = targets
        if not self.market:
            self.market = targets[0]
        return self


RecommendationSortType = Literal[
    "spread_desc",
    "bt_return_desc",
    "bt_excess_desc",
    "bt_mdd_asc",
    "bt_win_rate_desc",
]


class RecommendationPrefsUpdate(BaseModel):
    sort_by: RecommendationSortType = Field(default="spread_desc")
    exclude_negative_bt: bool = Field(default=False)


class BatchBacktestRequest(BaseModel):
    markets: list[str] | None = None
    force: bool = False


class SettingUpdate(BaseModel):
    expected_high_percentage: int = Field(ge=1, le=1000)
    expected_low_percentage: int = Field(ge=-99, le=1000)
    highest_price_reference_days: int = Field(ge=3, le=200)
    volume_check: bool

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.expected_low_percentage >= self.expected_high_percentage:
            raise ValueError("하한 비율은 목표 상승률보다 작아야 합니다.")
        return self


class Database:
    @contextmanager
    def connection(self):
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=3) as connection:
            yield connection

    def one(self, query: str, params=()):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def all(self, query: str, params=()):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute(self, query: str, params=()):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def executemany(self, query: str, params):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.executemany(query, params)


db = Database()
engine = TradingEngine(db, CALCULATION_SERVICE_URL, TRADING_ENABLED)
_public_ip_cache = {"value": None, "checked_at": 0.0}


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_upbit_credentials(db,SESSION_SECRET)
    try:
        db.execute("""UPDATE tb_user SET user_role='MASTER'
            WHERE deleted_at IS NULL AND (SELECT COUNT(*) FROM tb_user WHERE deleted_at IS NULL) = 1""")
        db.execute("""ALTER TABLE upbit_strategy_settings
            ADD COLUMN IF NOT EXISTS candle_interval VARCHAR(16) NOT NULL DEFAULT 'days',
            ADD COLUMN IF NOT EXISTS days INTEGER NOT NULL DEFAULT 180,
            ADD COLUMN IF NOT EXISTS initial_capital DOUBLE PRECISION NOT NULL DEFAULT 1000000,
            ADD COLUMN IF NOT EXISTS fee_bps DOUBLE PRECISION NOT NULL DEFAULT 5,
            ADD COLUMN IF NOT EXISTS slippage_bps DOUBLE PRECISION NOT NULL DEFAULT 10,
            ADD COLUMN IF NOT EXISTS auto_trade BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS sort_by VARCHAR(32) NOT NULL DEFAULT 'spread_desc',
            ADD COLUMN IF NOT EXISTS exclude_negative_bt BOOLEAN NOT NULL DEFAULT FALSE""")
        db.execute("""ALTER TABLE upbit
            ADD COLUMN IF NOT EXISTS bt_return_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS bt_benchmark_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS bt_excess_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS bt_mdd_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS bt_trade_count INTEGER,
            ADD COLUMN IF NOT EXISTS bt_win_rate_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS bt_candle_interval VARCHAR(16),
            ADD COLUMN IF NOT EXISTS bt_ma_period INTEGER,
            ADD COLUMN IF NOT EXISTS bt_updated_at VARCHAR(255)""")
    except Exception:
        pass
    engine.start()
    try:
        yield
    finally:
        engine.stop()


app = FastAPI(title="Trading API", version="2.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # FastAPI normally echoes the rejected input, which can contain passwords/API keys.
    details = [{"type": item["type"], "loc": item["loc"], "msg": item["msg"],
                "ctx": {k: v for k, v in item.get("ctx", {}).items() if isinstance(v, (str, int, float, bool))}}
               for item in error.errors()]
    return JSONResponse({"detail": details}, status_code=422)


@app.middleware("http")
async def prevent_private_response_caching(request, call_next):
    response = await call_next(request)
    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def serializer() -> URLSafeTimedSerializer:
    if len(SESSION_SECRET) < 32:
        raise RuntimeError("SESSION_SECRET must contain at least 32 characters")
    return URLSafeTimedSerializer(SESSION_SECRET, salt="trading-session")


def current_user(session: Annotated[str | None, Cookie()] = None) -> dict:
    if not session:
        raise HTTPException(401, "로그인이 필요합니다.")
    try:
        signed = serializer().loads(session, max_age=SESSION_MAX_AGE)
        if not isinstance(signed,dict) or not isinstance(signed.get('version'),int):
            raise HTTPException(401, '세션이 만료되었습니다.')
        login_id = signed.get('login_id')
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "세션이 만료되었습니다.")
    user = db.one(
        """SELECT id, user_login_id, user_name, user_role, user_email, user_phone, session_version
           FROM tb_user WHERE user_login_id=%s AND deleted_at IS NULL""",
        (login_id,),
    )
    if not user or user.get('session_version',0) != signed['version']:
        raise HTTPException(401, "사용자를 찾을 수 없습니다.")
    if user.get("user_role") == "USER":
        try:
            cnt = db.one("SELECT COUNT(*) AS c FROM tb_user WHERE deleted_at IS NULL")
            if cnt and (cnt.get("c") == 1 or cnt.get("count") == 1):
                db.execute("UPDATE tb_user SET user_role='MASTER' WHERE id=%s", (user["id"],))
                user["user_role"] = "MASTER"
        except Exception:
            pass
    return user


def admin_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["user_role"] not in {"ADMIN", "MASTER"}:
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    return user


def master_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["user_role"] != "MASTER":
        raise HTTPException(403, "MASTER 권한이 필요합니다.")
    return user


def dependency_health():
    database = "DOWN"
    calculation = "DOWN"
    try:
        database = "UP" if db.one("SELECT 1") else "DOWN"
    except Exception:
        pass
    try:
        calculation = "UP" if httpx.get(f"{CALCULATION_SERVICE_URL}/health", timeout=2).is_success else "DOWN"
    except httpx.HTTPError:
        pass
    status = "UP" if database == calculation == "UP" else "DEGRADED"
    return {"status": status, "database": database, "calculation": calculation}


@app.get("/api/health")
def health():
    state = dependency_health()
    return JSONResponse(state, status_code=200 if state["status"] == "UP" else 503)


@app.get("/api/system/public-ip")
def public_ip(_: Annotated[dict, Depends(current_user)]):
    """Public egress IP that must be allow-listed in the Upbit API key."""
    if _public_ip_cache["value"] and time.monotonic() - _public_ip_cache["checked_at"] < 300:
        return {"public_ip": _public_ip_cache["value"], "cached": True}
    for url in ("https://api64.ipify.org", "https://checkip.amazonaws.com"):
        try:
            value = httpx.get(url, timeout=4).text.strip()
            ip_address(value)
            _public_ip_cache.update(value=value, checked_at=time.monotonic())
            return {"public_ip": value, "cached": False}
        except (httpx.HTTPError, ValueError):
            continue
    raise HTTPException(503, "서버의 공인 IP를 확인하지 못했습니다. 서버에서 직접 확인해 주세요.")


def get_global_strategy_settings() -> dict:
    defaults = {
        "candle_interval": "days",
        "ma_period": 40,
        "days": 180,
        "initial_capital": 1_000_000.0,
        "fee_bps": 5.0,
        "slippage_bps": 10.0,
        "sort_by": "spread_desc",
        "exclude_negative_bt": False,
    }
    try:
        rows = db.all("SELECT * FROM upbit_strategy_settings ORDER BY CASE WHEN market='__GLOBAL__' THEN 0 ELSE 1 END, updated_at DESC")
    except Exception:
        rows = []
    if not rows or not isinstance(rows[0], dict):
        return defaults
    row = rows[0]
    candle_interval = str(row.get("candle_interval") or "days")
    if candle_interval not in {"15m", "30m", "60m", "240m", "days", "weeks"}:
        candle_interval = "days"
    ma_period = int(row.get("ma_period") or 40)
    raw_days = int(row.get("days") or 180)
    days = min(200, max(60, ma_period + 2, raw_days))
    sort_by = str(row.get("sort_by") or "spread_desc")
    if sort_by not in {"spread_desc", "bt_return_desc", "bt_excess_desc", "bt_mdd_asc", "bt_win_rate_desc"}:
        sort_by = "spread_desc"
    return {
        "candle_interval": candle_interval,
        "ma_period": ma_period,
        "days": days,
        "initial_capital": float(row.get("initial_capital") or 1_000_000.0),
        "fee_bps": float(row.get("fee_bps") if row.get("fee_bps") is not None else 5.0),
        "slippage_bps": float(row.get("slippage_bps") if row.get("slippage_bps") is not None else 10.0),
        "sort_by": sort_by,
        "exclude_negative_bt": bool(row.get("exclude_negative_bt") or False),
    }


@app.post("/api/backtest")
def run_backtest(payload: BacktestRun, _: Annotated[dict, Depends(current_user)]):
    global_cfg = get_global_strategy_settings()
    explicit = payload.model_fields_set
    candle_interval = payload.candle_interval if "candle_interval" in explicit else global_cfg["candle_interval"]
    ma_period = payload.ma_period if "ma_period" in explicit else global_cfg["ma_period"]
    days = payload.days if "days" in explicit else max(global_cfg["days"], ma_period + 2)
    initial_capital = payload.initial_capital if "initial_capital" in explicit else global_cfg["initial_capital"]
    fee_bps = payload.fee_bps if "fee_bps" in explicit else global_cfg["fee_bps"]
    slippage_bps = payload.slippage_bps if "slippage_bps" in explicit else global_cfg["slippage_bps"]
    is_intraday = candle_interval in {"15m", "30m", "60m", "240m"}
    candle_path = engine.upbit_candle_path(candle_interval)
    try:
        rows = engine.upbit_public(candle_path, {"market": payload.market, "count": days})
        candles = [{
            "date": (
                str(row["candle_date_time_kst"])[:16].replace("T", " ")
                if is_intraday
                else str(row["candle_date_time_kst"])[:10]
            ),
            "open": row["opening_price"],
            "close": row["trade_price"],
        } for row in rows]
        result = engine.calc("/v1/backtests/ma40", {"candles": candles,
            "ma_period": ma_period, "initial_capital": initial_capital, "fee_bps": fee_bps,
            "slippage_bps": slippage_bps})
        if "win_rate_pct" not in result:
            trades = result.get("trades") or []
            sells = [t for t in trades if isinstance(t, dict) and t.get("side") == "SELL"]
            buys = [t for t in trades if isinstance(t, dict) and t.get("side") == "BUY"]
            wins = 0
            for idx_s, sell in enumerate(sells):
                buy_val = float(buys[idx_s].get("value") or initial_capital) if idx_s < len(buys) else float(initial_capital)
                if float(sell.get("value") or 0) > buy_val:
                    wins += 1
            result = {
                **result,
                "win_rate_pct": round(wins * 100.0 / len(sells), 2) if sells else 0.0,
            }
        try:
            now_str = engine.now()
            db.execute(
                """UPDATE upbit
                   SET bt_return_pct=%s, bt_benchmark_pct=%s, bt_excess_pct=%s,
                       bt_mdd_pct=%s, bt_trade_count=%s, bt_win_rate_pct=%s,
                       bt_candle_interval=%s, bt_ma_period=%s, bt_updated_at=%s
                   WHERE code=%s AND deleted_at IS NULL""",
                (
                    round(float(result.get("return_pct") or 0.0), 2),
                    round(float(result.get("benchmark_return_pct") or 0.0), 2),
                    round(float(result.get("excess_return_pct") or 0.0), 2),
                    round(float(result.get("max_drawdown_pct") or 0.0), 2),
                    int(result.get("trade_count") or 0),
                    round(float(result.get("win_rate_pct") or 0.0), 2),
                    candle_interval,
                    ma_period,
                    now_str,
                    payload.market,
                ),
            )
        except Exception:
            pass
        return {
            "market": payload.market,
            "candle_interval": candle_interval,
            "days": len(candles),
            "ma_period": ma_period,
            **result,
        }
    except httpx.HTTPError as error:
        engine.record_error("UPBIT", "BACKTEST", error)
        raise HTTPException(502, "백테스트 시세를 불러오지 못했습니다.") from None


@app.post("/api/backtest/batch")
def run_batch_backtest(payload: BatchBacktestRequest, _: Annotated[dict, Depends(current_user)]):
    global_cfg = get_global_strategy_settings()
    candle_interval = global_cfg["candle_interval"]
    ma_period = global_cfg["ma_period"]
    days = max(global_cfg["days"], ma_period + 2)
    initial_capital = global_cfg["initial_capital"]
    fee_bps = global_cfg["fee_bps"]
    slippage_bps = global_cfg["slippage_bps"]
    try:
        rows = db.all(
            """SELECT code, bt_return_pct, bt_candle_interval, bt_ma_period
               FROM upbit WHERE deleted_at IS NULL ORDER BY id DESC"""
        )
    except Exception:
        rows = db.all("SELECT code FROM upbit WHERE deleted_at IS NULL")
    target_set = set(payload.markets) if payload.markets else None
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("code"):
            continue
        code = row["code"]
        if target_set is not None and code not in target_set:
            continue
        if (
            not payload.force
            and row.get("bt_return_pct") is not None
            and row.get("bt_candle_interval") == candle_interval
            and int(row.get("bt_ma_period") or 0) == ma_period
        ):
            continue
        candidates.append(code)
    updated = []
    now_str = engine.now()
    for code in candidates[:60]:
        try:
            prices = (
                engine.upbit_prices(code, days)
                if candle_interval == "days"
                else engine.upbit_prices(code, days, candle_interval)
            )
            if not prices:
                continue
            bt = engine.evaluate_ma_backtest(prices, ma_period, initial_capital, fee_bps, slippage_bps)
            try:
                db.execute(
                    """UPDATE upbit
                       SET bt_return_pct=%s, bt_benchmark_pct=%s, bt_excess_pct=%s,
                           bt_mdd_pct=%s, bt_trade_count=%s, bt_win_rate_pct=%s,
                           bt_candle_interval=%s, bt_ma_period=%s, bt_updated_at=%s
                       WHERE code=%s AND deleted_at IS NULL""",
                    (
                        bt["bt_return_pct"],
                        bt["bt_benchmark_pct"],
                        bt["bt_excess_pct"],
                        bt["bt_mdd_pct"],
                        bt["bt_trade_count"],
                        bt["bt_win_rate_pct"],
                        candle_interval,
                        ma_period,
                        now_str,
                        code,
                    ),
                )
            except Exception:
                pass
            updated.append({
                "code": code,
                **bt,
                "bt_candle_interval": candle_interval,
                "bt_ma_period": ma_period,
                "bt_updated_at": now_str,
            })
        except Exception as error:
            engine.record_error("UPBIT", "BATCH_BACKTEST", error)
    items_by_code = {row["code"]: row for row in updated}
    return {"ok": True, "updated_count": len(updated), "items": items_by_code}


@app.put("/api/upbit/recommendation-prefs")
def update_recommendation_prefs(payload: RecommendationPrefsUpdate, _: Annotated[dict, Depends(current_user)]):
    global_cfg = get_global_strategy_settings()
    try:
        db.execute(
            """INSERT INTO upbit_strategy_settings(
                   market, candle_interval, ma_period, days, initial_capital, fee_bps, slippage_bps,
                   sort_by, exclude_negative_bt, updated_at
               )
               VALUES('__GLOBAL__', %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT(market) DO UPDATE SET
                 sort_by=EXCLUDED.sort_by,
                 exclude_negative_bt=EXCLUDED.exclude_negative_bt,
                 updated_at=CURRENT_TIMESTAMP""",
            (
                global_cfg["candle_interval"],
                global_cfg["ma_period"],
                global_cfg["days"],
                global_cfg["initial_capital"],
                global_cfg["fee_bps"],
                global_cfg["slippage_bps"],
                payload.sort_by,
                payload.exclude_negative_bt,
            ),
        )
    except Exception:
        db.execute(
            """INSERT INTO upbit_strategy_settings(market, ma_period, sort_by, exclude_negative_bt, updated_at)
               VALUES('__GLOBAL__', %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT(market) DO UPDATE SET
                 sort_by=EXCLUDED.sort_by,
                 exclude_negative_bt=EXCLUDED.exclude_negative_bt,
                 updated_at=CURRENT_TIMESTAMP""",
            (global_cfg["ma_period"], payload.sort_by, payload.exclude_negative_bt),
        )
    return {
        "ok": True,
        "sort_by": payload.sort_by,
        "exclude_negative_bt": payload.exclude_negative_bt,
    }


@app.get("/api/strategies")
def market_strategies(_: Annotated[dict, Depends(current_user)]):
    global_cfg = get_global_strategy_settings()
    items = [r for r in db.all("SELECT market,ma_period,updated_at FROM upbit_strategy_settings ORDER BY market")
             if isinstance(r, dict) and r.get("market") != "__GLOBAL__"]
    return {
        **global_cfg,
        "default_ma_period": global_cfg["ma_period"],
        "items": items,
    }


@app.put("/api/strategies")
def save_market_strategy(payload: MarketStrategyUpdate, _: Annotated[dict, Depends(current_user)]):
    prev_cfg = get_global_strategy_settings()
    if payload.market == "__GLOBAL__":
        try:
            db.execute("DELETE FROM upbit_strategy_settings WHERE market <> '__GLOBAL__' AND COALESCE(auto_trade, false) = false")
            db.execute(
                "UPDATE upbit_strategy_settings SET ma_period=%s, candle_interval=%s, updated_at=CURRENT_TIMESTAMP WHERE market <> '__GLOBAL__'",
                (payload.ma_period, payload.candle_interval),
            )
        except Exception:
            try:
                db.execute("UPDATE upbit_strategy_settings SET ma_period=%s, updated_at=CURRENT_TIMESTAMP WHERE market <> '__GLOBAL__'", (payload.ma_period,))
            except Exception:
                db.execute("DELETE FROM upbit_strategy_settings WHERE market <> '__GLOBAL__'")
    try:
        db.execute(
            """INSERT INTO upbit_strategy_settings(market,candle_interval,ma_period,days,initial_capital,fee_bps,slippage_bps,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
               ON CONFLICT(market) DO UPDATE SET
                 candle_interval=EXCLUDED.candle_interval,
                 ma_period=EXCLUDED.ma_period,
                 days=EXCLUDED.days,
                 initial_capital=EXCLUDED.initial_capital,
                 fee_bps=EXCLUDED.fee_bps,
                 slippage_bps=EXCLUDED.slippage_bps,
                 updated_at=CURRENT_TIMESTAMP""",
            (payload.market, payload.candle_interval, payload.ma_period, payload.days, payload.initial_capital, payload.fee_bps, payload.slippage_bps),
        )
    except Exception:
        db.execute(
            """INSERT INTO upbit_strategy_settings(market,ma_period,updated_at)
               VALUES(%s,%s,CURRENT_TIMESTAMP) ON CONFLICT(market) DO UPDATE
               SET ma_period=EXCLUDED.ma_period,updated_at=CURRENT_TIMESTAMP""",
            (payload.market, payload.ma_period),
        )
    recollect_started = False
    if payload.market == "__GLOBAL__" and getattr(engine, "enabled", False):
        changed = (
            prev_cfg.get("candle_interval") != payload.candle_interval
            or prev_cfg.get("ma_period") != payload.ma_period
        )
        engine.trigger_collect_upbit(clear_stale=changed)
        recollect_started = True
    return {
        "ok": True,
        "market": payload.market,
        "candle_interval": payload.candle_interval,
        "ma_period": payload.ma_period,
        "days": payload.days,
        "initial_capital": payload.initial_capital,
        "fee_bps": payload.fee_bps,
        "slippage_bps": payload.slippage_bps,
        "recollect_started": recollect_started,
        "note": "변경된 캔들 기준으로 추천 신호를 즉시 재계산합니다." if recollect_started else "다음 신호 수집 및 백테스트부터 적용됩니다.",
    }


@app.post("/api/upbit/recollect")
def recollect_upbit_signals(_: Annotated[dict, Depends(current_user)]):
    res = engine.trigger_collect_upbit(clear_stale=False)
    return {"ok": True, **res, "signal_collection": engine.collection_status()}


@app.put("/api/upbit/auto-markets")
def update_market_auto_trade(payload: MarketAutoTradeUpdate, _: Annotated[dict, Depends(current_user)]):
    global_cfg = get_global_strategy_settings()
    targets = payload.markets or ([payload.market] if payload.market else [])
    for target in targets:
        try:
            db.execute(
                """INSERT INTO upbit_strategy_settings(market,ma_period,auto_trade,updated_at)
                   VALUES(%s,%s,%s,CURRENT_TIMESTAMP)
                   ON CONFLICT(market) DO UPDATE SET
                     auto_trade=EXCLUDED.auto_trade,
                     updated_at=CURRENT_TIMESTAMP""",
                (target, global_cfg["ma_period"], payload.auto_trade),
            )
        except Exception:
            db.execute(
                """INSERT INTO upbit_strategy_settings(market,ma_period,updated_at)
                   VALUES(%s,%s,CURRENT_TIMESTAMP) ON CONFLICT(market) DO UPDATE
                   SET ma_period=EXCLUDED.ma_period,updated_at=CURRENT_TIMESTAMP""",
                (target, global_cfg["ma_period"]),
            )
    return {
        "ok": True,
        "market": payload.market,
        "markets": targets,
        "auto_trade": payload.auto_trade,
    }


@app.delete("/api/strategies/{market}", status_code=204)
def delete_market_strategy(market: str, _: Annotated[dict, Depends(current_user)]):
    if market != "__GLOBAL__" and not market.startswith("KRW-"):
        raise HTTPException(422, "올바른 KRW 마켓을 입력해 주세요.")
    db.execute("DELETE FROM upbit_strategy_settings WHERE market=%s", (market,))


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response, request: Request):
    peer = request.client.host if request.client else 'unknown'
    # Only our local Cloudflare connector may assert the original client address.
    try:
        trusted = ip_address(peer).is_loopback or peer in os.environ.get('TRUSTED_PROXY_IPS','172.18.0.1').split(',')
        client_ip = str(ip_address(request.headers.get('CF-Connecting-IP',peer))) if trusted else peer
    except ValueError:
        client_ip = peer
    def verify():
        user = db.one(
        """SELECT user_login_id, user_name, user_role, user_password, session_version
           FROM tb_user WHERE user_login_id=%s AND deleted_at IS NULL""",
        (payload.login_id,),
    )
        try:
            matched = bcrypt.checkpw(payload.password.encode(), (user["user_password"] if user else DUMMY_PASSWORD_HASH).encode())
            valid = bool(user and matched)
        except (ValueError, TypeError):
            valid = False
        return user if valid else None
    user = authenticate(db,payload.login_id,client_ip,verify)
    if not user:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    response.set_cookie(
        "session", serializer().dumps({'login_id':user['user_login_id'],'version':user.get('session_version',0)}), max_age=SESSION_MAX_AGE,
        httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/",
    )
    return {key: user[key] for key in ("user_login_id", "user_name", "user_role")}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, user: Annotated[dict, Depends(current_user)]):
    db.execute('UPDATE tb_user SET session_version=session_version+1 WHERE id=%s',(user['id'],))
    response.delete_cookie("session", path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")


@app.get("/api/auth/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return user


@app.get("/api/recommendations/{market}")
def recommendations(market: Literal["stock", "upbit"], user: Annotated[dict, Depends(current_user)],
                    include_ownership: bool = True):
    rows = db.all(
        f"""SELECT code, name, origin_minimum_selling_price, origin_expected_selling_price,
                    minimum_selling_price, expected_selling_price, temp_price, setting_price,
                    renewal_cnt, pricing_reference_date, updated_at
             FROM {market} WHERE deleted_at IS NULL
             ORDER BY renewal_cnt DESC,
                      (expected_selling_price-temp_price)
                        / NULLIF(expected_selling_price-minimum_selling_price, 0) ASC NULLS LAST,
                      id DESC"""
    )
    if market == "upbit" and include_ownership:
        key = db.one("SELECT user_login_id,access_key,secret_key FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
        owned = {}
        ownership_available = True
        if key:
            try:
                accounts = engine.private_for_key("GET", "/v1/accounts", key)
                owned = {row["currency"]: float(row["balance"]) + float(row["locked"]) for row in accounts}
            except (httpx.HTTPError, ValueError) as error:
                ownership_available = False
                engine.record_error("UPBIT", "RECOMMENDATION_BALANCE", error)
        for row in rows:
            currency = row["code"].removeprefix("KRW-")
            row["owned"] = owned.get(currency, 0) > 0 if ownership_available else None
            row["owned_quantity"] = owned.get(currency, 0) if ownership_available else None
    if market=='stock':
        for row in rows:row.update(market_region='US' if is_us_symbol(row['code']) else 'KR',currency='USD' if is_us_symbol(row['code']) else 'KRW')
    return rows


@app.get("/api/dividends")
def dividends(_: Annotated[dict, Depends(current_user)]):
    rows=db.all("""SELECT code,name,dividend_rate,ex_div_date,pay_date,updated_at,created_at FROM dividend_stock
        WHERE deleted_at IS NULL ORDER BY dividend_rate DESC""")
    for row in rows:
        us=is_us_symbol(row['code'])
        row.update(market_region='US' if us else 'KR',currency='USD' if us else 'KRW',
                   yield_basis='최근 12개월 배당 이벤트 합계 / 최근 종가' if us else '국내 제공자 배당수익률',
                   data_source='Yahoo Finance 공개 일봉·배당 이벤트' if us else '네이버 금융')
    return rows


@app.get("/api/orders")
def order_history(user: Annotated[dict, Depends(current_user)]):
    key = db.one("SELECT user_login_id,access_key,secret_key FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
    if key:
        try:
            engine.sync_orders(user["user_login_id"], *engine.key_credentials(key,user["user_login_id"]))
        except httpx.HTTPError as error:
            engine.record_error("UPBIT", "SYNC_ORDER_HISTORY", error)
    return db.all("""SELECT uuid,side,ord_type,price,state,market,created_at,volume,executed_volume
        FROM upbit_order_history WHERE login_id=%s AND deleted_at IS NULL ORDER BY id DESC LIMIT 200""",
        (user["user_login_id"],))


@app.get("/api/admin/system")
def system(_: Annotated[dict, Depends(admin_user)]):
    state = dependency_health()
    error_count = db.one("SELECT count(*) AS count FROM trade_error_log")["count"]
    return {**state, "api_uptime_seconds": int(time.monotonic() - STARTED_AT), "error_count": error_count,
            "trading_execution": "ACTIVE" if TRADING_ENABLED else "DISABLED",
            "scheduler_running": engine.scheduler.running}


class PasswordPayload(BaseModel):
    @field_validator("password", check_fields=False)
    @classmethod
    def validate_password_bytes(cls, value):
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("비밀번호는 UTF-8 기준 72바이트 이하여야 합니다.")
        return value


class JoinRequest(PasswordPayload):
    login_id: str = Field(min_length=4, max_length=50)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=25)


class ProfileUpdate(PasswordPayload):
    current_password: str | None = Field(None, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=25)
    password: str | None = Field(None, min_length=8, max_length=200)


class UpbitKeyUpdate(BaseModel):
    access_key: str = Field(min_length=1, max_length=255)
    secret_key: str = Field(min_length=1, max_length=255)


class MarketSellRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str = Field(pattern=r"^KRW-[A-Z0-9]{1,20}$")
    expected_available_quantity: Decimal = Field(gt=0, max_digits=40, decimal_places=20)
    confirm: Literal[True]
    keep_auto: Literal[True]


class MailTarget(BaseModel):
    email: str = Field(min_length=3, max_length=255)


@app.get("/api/auth/check-id")
def check_login_id(login_id: str = Query(..., min_length=1, max_length=50)):
    if not SIGNUP_ENABLED:
        raise HTTPException(403, "회원가입이 비활성화되어 있습니다.")
    cleaned = login_id.strip()
    if len(cleaned) < 4 or len(cleaned) > 50 or not re.match(r"^[a-zA-Z0-9_.-]{4,50}$", cleaned):
        return {
            "available": False,
            "login_id": cleaned,
            "reason": "아이디는 영문, 숫자, 밑줄(_), 하이픈(-), 마침표(.) 조합 4~50자로 입력해 주세요.",
        }
    exists = db.one("SELECT id FROM tb_user WHERE user_login_id=%s", (cleaned,))
    if exists:
        return {
            "available": False,
            "login_id": cleaned,
            "reason": "이미 사용 중인 아이디입니다.",
        }
    return {
        "available": True,
        "login_id": cleaned,
        "reason": "사용 가능한 아이디입니다.",
    }


@app.post("/api/auth/join", status_code=201)
def join(payload: JoinRequest):
    if not SIGNUP_ENABLED:
        raise HTTPException(403,'회원가입이 비활성화되어 있습니다.')
    if SINGLE_USER_ONLY and db.one("SELECT id FROM tb_user WHERE deleted_at IS NULL LIMIT 1"):
        raise HTTPException(403, "최초 계정이 이미 생성되어 회원가입이 잠겼습니다.")
    login_id = payload.login_id.strip()
    name = payload.name.strip()
    if len(login_id) < 4:
        raise HTTPException(400, "아이디는 4자 이상이어야 합니다.")
    if not name:
        raise HTTPException(400, "이름을 입력해 주세요.")
    if db.one("SELECT id FROM tb_user WHERE user_login_id=%s", (login_id,)):
        raise HTTPException(409, "이미 사용 중인 아이디입니다.")
    has_active_user = bool(db.one("SELECT id FROM tb_user WHERE deleted_at IS NULL LIMIT 1"))
    role = "USER" if has_active_user else "MASTER"
    password = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    now = engine.now()
    email = payload.email.strip() if payload.email and payload.email.strip() else None
    phone = payload.phone.strip() if payload.phone and payload.phone.strip() else None
    db.execute(f"""INSERT INTO tb_user(id,user_login_id,user_password,user_name,user_role,user_email,user_phone,
        created_at,updated_at,deleted_at) VALUES(nextval('tb_user_seq'),%s,%s,%s,'{role}',%s,%s,%s,NULL,NULL)""",
        (login_id, password, name, email, phone, now))
    return {"ok": True}


@app.put("/api/profile")
def update_profile(payload: ProfileUpdate, user: Annotated[dict, Depends(current_user)]):
    if payload.password:
        existing=db.one('SELECT user_password FROM tb_user WHERE id=%s',(user['id'],))
        try:
            valid=bool(payload.current_password and existing and bcrypt.checkpw(payload.current_password.encode(),existing['user_password'].encode()))
        except (ValueError,TypeError):
            valid=False
        if not valid:raise HTTPException(400,'현재 비밀번호가 올바르지 않습니다.')
    encoded = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode() if payload.password else None
    phone = payload.phone if "phone" in payload.model_fields_set else user.get("user_phone")
    changed = db.execute("""UPDATE tb_user SET user_name=%s,user_email=%s,user_phone=%s,
        user_password=COALESCE(%s,user_password),updated_at=%s,
        session_version=session_version+%s WHERE id=%s AND (%s IS NULL OR user_password=%s)""",
        (payload.name,payload.email,phone,encoded,engine.now(),1 if encoded else 0,user["id"],encoded,existing['user_password'] if encoded else None))
    if changed == 0:
        raise HTTPException(409,'계정 정보가 변경되었습니다. 다시 로그인해 주세요.')
    return {"ok": True}


@app.get('/api/auth/config')
def auth_config():
    return {'signup_enabled':SIGNUP_ENABLED}


@app.post('/api/upbit/auto-orders/reconcile')
def reconcile_orders(user: Annotated[dict, Depends(master_user)]):
    key=db.one('SELECT * FROM tb_upbit_key WHERE user_login_id=%s',(user['user_login_id'],))
    if not key:raise HTTPException(404,'등록된 Upbit 키가 없습니다.')
    try:return engine.reconcile_only(key)
    except ValueError as error:raise HTTPException(409,str(error)) from None


@app.get("/api/upbit/key/status")
def upbit_key_status(user: Annotated[dict, Depends(current_user)]):
    row=db.one("""SELECT EXISTS(SELECT 1 FROM tb_upbit_key
        WHERE user_login_id=%s AND COALESCE(access_key,'')<>'' AND COALESCE(secret_key,'')<>'') AS registered""",
        (user["user_login_id"],))
    return {"registered": bool(row and row["registered"])}


@app.put("/api/upbit/key")
def save_upbit_key(payload: UpbitKeyUpdate, user: Annotated[dict, Depends(current_user)]):
    access=encrypt_upbit(SESSION_SECRET,user['user_login_id'],payload.access_key)
    secret=encrypt_upbit(SESSION_SECRET,user['user_login_id'],payload.secret_key)
    existing=db.one("SELECT id FROM tb_upbit_key WHERE user_login_id=%s",(user["user_login_id"],))
    if existing:
        db.execute("UPDATE tb_upbit_key SET access_key=%s,secret_key=%s WHERE id=%s",
                   (access,secret,existing["id"]))
    else:
        db.execute("INSERT INTO tb_upbit_key(id,user_login_id,access_key,secret_key,auto_on) VALUES(nextval('tb_upbit_key_seq'),%s,%s,%s,false)",
                   (user["user_login_id"],access,secret))
    return {"ok": True}


@app.get("/api/upbit/accounts")
def upbit_accounts(user: Annotated[dict, Depends(current_user)]):
    key=db.one("SELECT * FROM tb_upbit_key WHERE user_login_id=%s",(user["user_login_id"],))
    if not key: return {"total_valuation": 0, "valuation_complete": True, "unpriced_currencies": [], "assets": []}
    try:
        return engine.account_snapshot(*engine.key_credentials(key,user["user_login_id"]))
    except httpx.HTTPError as error:
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        engine.record_error("UPBIT", "GET_ACCOUNT" if status is None else f"GET_ACCOUNT_HTTP_{status}", error)
        if status in (401,403) and error.request.url.path == "/v1/accounts":
            db.execute("UPDATE tb_upbit_key SET auto_on=false WHERE id=%s AND access_key=%s AND secret_key=%s",
                       (key["id"], key["access_key"], key["secret_key"]))
        raise HTTPException(502,"Upbit 계좌 조회에 실패했습니다.")


@app.get("/api/dashboard")
def dashboard(user: Annotated[dict, Depends(current_user)]):
    key = db.one("SELECT * FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
    creds = None
    snapshot = {"total_valuation": 0, "valuation_complete": True, "unpriced_currencies": [], "assets": []}
    if key:
        try:
            creds = engine.key_credentials(key,user["user_login_id"])
            snapshot = engine.account_snapshot(*creds)
        except httpx.HTTPError as error:
            engine.record_error("UPBIT", "GET_DASHBOARD_ACCOUNT", error)
            raise HTTPException(502, "대시보드 계좌 조회에 실패했습니다.") from None
    invested = sum(float(row.get("purchase_amount") or 0) for row in snapshot["assets"] if row.get("currency") != "KRW")
    valued = sum(float(row.get("valuation") or 0) for row in snapshot["assets"] if row.get("currency") != "KRW")
    unrealized = valued - invested if invested else None
    db.execute("""INSERT INTO portfolio_daily_snapshot(user_id,snapshot_date,total_valuation,purchase_amount,unrealized_profit)
        VALUES(%s,CURRENT_DATE,%s,%s,%s) ON CONFLICT(user_id,snapshot_date) DO UPDATE SET
        total_valuation = CASE WHEN portfolio_daily_snapshot.total_valuation <= 0 THEN EXCLUDED.total_valuation ELSE portfolio_daily_snapshot.total_valuation END,
        purchase_amount = COALESCE(portfolio_daily_snapshot.purchase_amount, EXCLUDED.purchase_amount),
        unrealized_profit = COALESCE(portfolio_daily_snapshot.unrealized_profit, EXCLUDED.unrealized_profit)""",
        (user["id"], snapshot["total_valuation"], invested or None, unrealized))

    prior_snapshot = db.one("""SELECT total_valuation FROM portfolio_daily_snapshot
        WHERE user_id=%s AND snapshot_date < CURRENT_DATE AND total_valuation > 0
        ORDER BY snapshot_date DESC LIMIT 1""", (user["id"],))
    baseline = prior_snapshot or db.one("""SELECT total_valuation FROM portfolio_daily_snapshot
        WHERE user_id=%s AND snapshot_date = CURRENT_DATE AND total_valuation > 0""", (user["id"],))
    baseline_val = float(baseline["total_valuation"]) if baseline and baseline.get("total_valuation") else 0.0
    day_change = (snapshot["total_valuation"] - baseline_val) if (baseline_val > 0 and snapshot["total_valuation"] > 0) else None
    day_change_rate = (day_change * 100 / baseline_val) if (baseline_val > 0 and day_change is not None) else None

    strategy_settings = get_global_strategy_settings()
    try:
        auto_rows = db.all("SELECT market FROM upbit_strategy_settings WHERE auto_trade=true AND market <> '__GLOBAL__' ORDER BY market")
        auto_trade_markets = [r["market"] for r in auto_rows if isinstance(r, dict) and r.get("market")]
    except Exception:
        auto_trade_markets = []
    auto_trade_set = set(auto_trade_markets)
    raw_recommendations = db.all("""SELECT u.id,u.code,u.name,u.temp_price,u.minimum_selling_price,u.expected_selling_price,
        u.setting_price,u.renewal_cnt,u.updated_at,
        u.bt_return_pct,u.bt_benchmark_pct,u.bt_excess_pct,u.bt_mdd_pct,u.bt_trade_count,
        u.bt_win_rate_pct,u.bt_candle_interval,u.bt_ma_period,u.bt_updated_at,
        COALESCE(s.ma_period,40) AS ma_period,
        COALESCE(s.auto_trade,false) AS auto_trade FROM upbit u
        LEFT JOIN upbit_strategy_settings s ON s.market=u.code WHERE u.deleted_at IS NULL
        ORDER BY ((u.temp_price - u.setting_price) / NULLIF(u.setting_price, 0)) DESC NULLS LAST, u.id DESC""")
    prelim_recommendations = []
    for r in raw_recommendations:
        row_copy = dict(r)
        if not row_copy.get("ma_period") or row_copy.get("ma_period") == 40:
            row_copy["ma_period"] = strategy_settings["ma_period"]
        row_copy["candle_interval"] = strategy_settings["candle_interval"]
        temp_p = float(row_copy.get("temp_price") or 0)
        set_p = float(row_copy.get("setting_price") or 0)
        row_copy["spread_pct"] = round((temp_p - set_p) * 100.0 / set_p, 2) if set_p > 0 else None
        for bt_key in (
            "bt_return_pct",
            "bt_benchmark_pct",
            "bt_excess_pct",
            "bt_mdd_pct",
            "bt_trade_count",
            "bt_win_rate_pct",
            "bt_candle_interval",
            "bt_ma_period",
            "bt_updated_at",
        ):
            row_copy.setdefault(bt_key, None)
        is_enabled = bool(row_copy.get("auto_trade")) or (row_copy.get("code") in auto_trade_set)
        row_copy["auto_trade"] = is_enabled
        prelim_recommendations.append(row_copy)

    sorted_recommendations = sort_recommendation_rows(
        prelim_recommendations, strategy_settings.get("sort_by", "spread_desc")
    )
    recommendations = []
    auto_rank = 0
    exclude_neg = bool(strategy_settings.get("exclude_negative_bt"))
    for row_copy in sorted_recommendations:
        is_enabled = bool(row_copy.get("auto_trade"))
        bt_ret = row_copy.get("bt_return_pct")
        if exclude_neg and bt_ret is not None and float(bt_ret) < 0:
            row_copy["auto_trade_excluded_reason"] = "negative_bt"
            row_copy["auto_trade_rank"] = None
        elif is_enabled:
            row_copy["auto_trade_excluded_reason"] = None
            auto_rank += 1
            row_copy["auto_trade_rank"] = auto_rank
        else:
            row_copy["auto_trade_excluded_reason"] = None
            row_copy["auto_trade_rank"] = None
        recommendations.append(row_copy)

    active_rec_codes = {row.get("code") for row in recommendations if row.get("code")}
    missing_auto_codes = [m for m in auto_trade_markets if m not in active_rec_codes]
    inactive_auto_trade_items = []
    if missing_auto_codes:
        try:
            meta_rows = db.all(
                """SELECT m.code,
                          COALESCE(u.name, l.name, m.code) AS name,
                          u.temp_price,
                          u.setting_price,
                          u.updated_at,
                          u.deleted_at
                   FROM unnest(%s::text[]) AS m(code)
                   LEFT JOIN LATERAL (
                       SELECT name, temp_price, setting_price, updated_at, deleted_at
                       FROM upbit WHERE code = m.code ORDER BY id DESC LIMIT 1
                   ) u ON TRUE
                   LEFT JOIN LATERAL (
                       SELECT name, deleted_at
                       FROM upbit_history_label WHERE code = m.code ORDER BY id DESC LIMIT 1
                   ) l ON TRUE""",
                (missing_auto_codes,),
            )
        except Exception:
            meta_rows = []
        by_meta = {r["code"]: r for r in meta_rows if isinstance(r, dict) and r.get("code")}
        for code in missing_auto_codes:
            info = by_meta.get(code, {})
            inactive_auto_trade_items.append({
                "code": code,
                "name": info.get("name") or code,
                "temp_price": info.get("temp_price"),
                "setting_price": info.get("setting_price"),
                "updated_at": info.get("updated_at"),
                "deleted_at": info.get("deleted_at"),
                "candle_interval": strategy_settings["candle_interval"],
                "ma_period": strategy_settings["ma_period"],
                "auto_trade": True,
                "status": "SIGNAL_DROPPED",
            })

    if creds:
        try:
            pending_rows = db.all(
                """SELECT uuid, state FROM upbit_order_history
                   WHERE login_id=%s AND deleted_at IS NULL AND uuid IS NOT NULL
                     AND COALESCE(state, 'wait') NOT IN ('done', 'cancel')
                   ORDER BY id DESC LIMIT 100""",
                (user["user_login_id"],),
            )
            pending_uuids = [
                row["uuid"]
                for row in pending_rows
                if isinstance(row, dict)
                and row.get("uuid")
                and (row.get("state") or "wait") not in ("done", "cancel")
            ]
            if pending_uuids:
                engine.sync_order_uuids(user["user_login_id"], *creds, pending_uuids, target_db=db)
        except Exception as error:
            if isinstance(error, httpx.HTTPError):
                engine.record_error("UPBIT", "SYNC_DASHBOARD_ORDERS", error)

    recent_orders = db.all("""SELECT uuid,side,ord_type,price,state,market,created_at,volume,executed_volume
        FROM upbit_order_history WHERE login_id=%s AND deleted_at IS NULL ORDER BY id DESC LIMIT 5""",
        (user["user_login_id"],))

    today_orders = db.all("""SELECT uuid,side,ord_type,price,state,market,created_at,volume,executed_volume
        FROM upbit_order_history
        WHERE login_id=%s AND deleted_at IS NULL
          AND (CASE WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN substring(created_at from 1 for 10) END = CURRENT_DATE::text)
          AND (state = 'done' OR (executed_volume IS NOT NULL AND executed_volume::numeric > 0))
        ORDER BY id DESC LIMIT 10""", (user["user_login_id"],))

    rec_by_code = {row["code"]: row for row in recommendations}
    total_val = float(snapshot.get("total_valuation") or 0)
    enriched_assets = []
    for asset in snapshot["assets"]:
        currency = asset.get("currency")
        row = dict(asset)
        val = row.get("valuation")
        if val is not None and total_val > 0:
            row["weight_pct"] = round(float(val) * 100 / total_val, 1)
        if currency != "KRW":
            code = f"KRW-{currency}"
            rec = rec_by_code.get(code)
            row["in_recommendations"] = bool(rec)
            row["auto_trade"] = bool((rec and rec.get("auto_trade")) or (code in auto_trade_set))
            if rec:
                if rec.get("name"):
                    row["name"] = rec["name"]
                min_price = float(rec["minimum_selling_price"])
                exp_price = float(rec["expected_selling_price"])
                row["target_price"] = exp_price
                row["stop_loss_price"] = min_price
                row["setting_price"] = float(rec.get("setting_price") or 0)
                row["renewal_cnt"] = rec.get("renewal_cnt")
                curr = float(row.get("current_price") or rec.get("temp_price") or 0)
                if curr > 0:
                    row["distance_to_target_pct"] = round((exp_price - curr) * 100 / curr, 2)
                    row["distance_to_stop_pct"] = round((curr - min_price) * 100 / curr, 2)
                    span = exp_price - min_price
                    row["target_progress"] = max(0, min(100, round((curr - min_price) * 100 / span, 1))) if span > 0 else 0
        enriched_assets.append(row)
    snapshot["assets"] = enriched_assets

    latest_error = db.one("SELECT source,operation,error_type,message,COALESCE(last_seen_at,created_at) AS created_at FROM trade_error_log ORDER BY COALESCE(last_seen_at,created_at) DESC,id DESC LIMIT 1")
    latest_price = max((row.get("updated_at") for row in recommendations if row.get("updated_at")), default=None)
    now = time.time()
    price_age = None
    if latest_price:
        try:
            price_age = max(0, now - time.mktime(time.strptime(str(latest_price)[:19], "%Y-%m-%d %H:%M:%S")))
        except ValueError:
            pass

    price_healthy = price_age is not None and price_age <= 450
    auto_on = bool(key and key.get("auto_on"))
    key_registered = bool(key)
    unresolved_orders = db.all("""SELECT identifier,market,created_at FROM auto_order_requests
        WHERE key_id=%s AND status IN ('PENDING','UNKNOWN') ORDER BY created_at""",(key['id'],)) if key else []

    next_decision_seconds = None
    if hasattr(engine, "scheduler") and engine.scheduler.running:
        job = engine.scheduler.get_job("trading-1")
        if job and job.next_run_time:
            now_utc = datetime.now(timezone.utc)
            next_decision_seconds = max(0, int((job.next_run_time - now_utc).total_seconds()))

    if unresolved_orders:
        safety_summary = f"자동매매 일시 중단: 접수 확인되지 않은 주문 {len(unresolved_orders)}건"
        safety_level = 'blocked'
    elif not key_registered:
        safety_summary = "Upbit API 키가 등록되지 않았습니다."
        safety_level = "warning"
    elif not auto_on:
        safety_summary = "자동매매가 중지되어 있습니다."
        safety_level = "neutral"
    elif not price_healthy:
        mins = max(1, int(price_age / 60)) if price_age else 1
        safety_summary = f"가격 갱신이 {mins}분간 지연되어 신규 매수를 일시 중지했습니다."
        safety_level = "delayed"
    else:
        time_str = str(latest_price)[11:16] if latest_price else "최근"
        next_sec = next_decision_seconds if next_decision_seconds is not None else 30
        safety_summary = f"자동매매 정상 작동 중 · 마지막 판단 {time_str} · 다음 판단 약 {next_sec}초 후"
        safety_level = "healthy"

    notifications = []
    if not key_registered:
        notifications.append({"id": "no-key", "level": "warning", "title": "API 키 미등록", "message": "Upbit API 키를 등록해야 잔고 조회 및 자동매매가 가능합니다."})
    elif not auto_on:
        notifications.append({"id": "auto-off", "level": "info", "title": "자동매매 꺼짐", "message": "자동매매가 꺼져 있어 신규 주문이 실행되지 않습니다."})
    if latest_price and not price_healthy:
        mins = max(1, int(price_age / 60)) if price_age else 1
        notifications.append({"id": "price-delay", "level": "warning", "title": "가격 갱신 지연", "message": f"가격 데이터가 {mins}분째 지연되고 있습니다."})
    if latest_error:
        notifications.append({"id": "recent-error", "level": "error", "title": f"{latest_error.get('source', '')} 오류", "message": latest_error.get("operation") or "오류가 기록되었습니다."})

    return {
        **snapshot,
        "auto_on": auto_on,
        "key_registered": key_registered,
        "strategy_settings": strategy_settings,
        "signal_collection": engine.collection_status() if hasattr(engine, "collection_status") else {"running": False},
        "auto_trade_markets": auto_trade_markets,
        "inactive_auto_trade_items": inactive_auto_trade_items,
        "recommendations": recommendations,
        "recent_orders": recent_orders,
        "today_orders": today_orders,
        "today_executed_count": len(today_orders),
        "performance": {
            "invested": invested or None,
            "unrealized_profit": unrealized,
            "unrealized_rate": round(unrealized * 100 / invested, 2) if invested else None,
            "today_change": round(day_change, 2) if day_change is not None else None,
            "today_change_rate": round(day_change_rate, 2) if day_change_rate is not None else None,
        },
        "safety": {
            "unresolved_orders": unresolved_orders,
            "unresolved_count": len(unresolved_orders),
            "summary": safety_summary,
            "level": safety_level,
            "price_updated_at": latest_price,
            "price_age_seconds": price_age,
            "price_healthy": price_healthy,
            "next_decision_seconds": next_decision_seconds,
            "latest_error": latest_error,
        },
        "notifications": notifications,
    }


@app.post("/api/upbit/orders/market-sell", status_code=201)
def market_sell(payload: MarketSellRequest, user: Annotated[dict, Depends(master_user)]):
    key = db.one("SELECT * FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
    if not key:
        raise HTTPException(404, "등록된 Upbit 키가 없습니다.")
    try:
        result = engine.manual_market_sell(key, payload.market, payload.expected_available_quantity)
        try:
            db.execute(
                "UPDATE upbit_strategy_settings SET auto_trade=false, updated_at=CURRENT_TIMESTAMP WHERE market=%s AND auto_trade=true",
                (payload.market,),
            )
        except Exception:
            pass
        if isinstance(result, dict):
            if result.get("uuid") and (result.get("state") or "wait") not in ("done", "cancel"):
                try:
                    synced = engine.sync_order_uuids(
                        user["user_login_id"],
                        *engine.key_credentials(key, user["user_login_id"]),
                        [result["uuid"]],
                        target_db=db,
                    )
                    if synced and synced[0].get("state"):
                        result = {**result, "state": synced[0]["state"]}
                except Exception:
                    pass
            return {**result, "auto_trade_disabled": True}
        return result
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    except httpx.HTTPError as error:
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        engine.record_error("UPBIT", "MANUAL_MARKET_SELL" if status is None else f"MANUAL_MARKET_SELL_HTTP_{status}", error)
        raise HTTPException(502, "시장가 매도 응답을 확인하지 못했습니다. 재주문하지 말고 주문 내역을 먼저 확인해 주세요.") from None


@app.put("/api/upbit/auto")
def own_auto(payload: AutoUpdate, user: Annotated[dict, Depends(current_user)]):
    if not db.one("SELECT id FROM tb_upbit_key WHERE user_login_id=%s",(user["user_login_id"],)):
        raise HTTPException(404,"등록된 Upbit 키가 없습니다.")
    db.execute("UPDATE tb_upbit_key SET auto_on=%s WHERE user_login_id=%s",(payload.auto_on,user["user_login_id"]))
    return {"ok": True}


@app.get("/api/admin/mail-targets")
def mail_targets(_: Annotated[dict, Depends(admin_user)]):
    return db.all("SELECT email FROM target_mail WHERE deleted_at IS NULL ORDER BY email")


@app.post("/api/admin/mail-targets", status_code=201)
def add_mail_target(payload: MailTarget, _: Annotated[dict, Depends(admin_user)]):
    existing=db.one("SELECT email FROM target_mail WHERE email=%s",(payload.email,))
    if existing: db.execute("UPDATE target_mail SET deleted_at=NULL,updated_at=%s WHERE email=%s",(engine.now(),payload.email))
    else: db.execute("INSERT INTO target_mail(email,created_at,updated_at,deleted_at) VALUES(%s,%s,NULL,NULL)",(payload.email,engine.now()))
    return {"ok":True}


@app.delete("/api/admin/mail-targets/{email}", status_code=204)
def delete_mail_target(email: str, _: Annotated[dict, Depends(admin_user)]):
    db.execute("UPDATE target_mail SET deleted_at=%s WHERE email=%s",(engine.now(),email))


@app.post("/api/admin/jobs/{job}")
def run_job(job: Literal["collect-stock","update-stock","collect-us-stock","update-us-stock","collect-us-dividends","collect-upbit","update-upbit","collect-dividends","auto-order","stock-history","upbit-history"],
            _: Annotated[dict, Depends(master_user)]):
    function={"collect-stock":engine.collect_stock,"update-stock":engine.update_stock,
              "collect-us-stock":engine.collect_us_stock,"update-us-stock":engine.update_us_stock,"collect-us-dividends":engine.collect_us_dividends,
              "collect-upbit":engine.collect_upbit,"update-upbit":engine.update_upbit,
              "collect-dividends":engine.collect_dividends,
              "auto-order":engine.auto_order,"stock-history":engine.save_stock_history,
              "upbit-history":engine.save_upbit_history}[job]
    result = function()
    status = result.get("status") if isinstance(result, dict) else None
    if status == "SKIPPED":
        raise HTTPException(409, "이미 실행 중인 작업입니다. 완료 후 다시 확인해 주세요.")
    if status in {"PARTIAL", "ERROR"}:
        raise HTTPException(502, "작업 중 오류가 발생했습니다. 일부 작업은 완료되었을 수 있으니 오류·주문 내역을 먼저 확인해 주세요.")
    return {"ok": True, "result": result}


@app.delete("/api/admin/recommendations/{market}", status_code=204)
def reset_recommendations(market: Literal["stock","upbit"], _: Annotated[dict, Depends(admin_user)]):
    db.execute(f"UPDATE {market} SET deleted_at=%s WHERE deleted_at IS NULL",(engine.now(),))


@app.get("/api/admin/errors")
def errors(
    _: Annotated[dict, Depends(admin_user)], page: int = Query(0, ge=0),
    source: str = Query("", max_length=20), keyword: str = Query("", max_length=100),
):
    filters, values = [], []
    if source.strip():
        filters.append("source = %s")
        values.append(source.strip())
    if keyword.strip():
        filters.append("(operation ILIKE %s OR error_type ILIKE %s OR message ILIKE %s)")
        values.extend([f"%{keyword.strip()}%"] * 3)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    total = db.one(f"SELECT count(*) AS count FROM trade_error_log{where}", values)["count"]
    rows = db.all(
        f"SELECT id, source, operation, error_type, message, created_at,repeat_count,COALESCE(last_seen_at,created_at) AS last_seen_at FROM trade_error_log{where} ORDER BY COALESCE(last_seen_at,created_at) DESC,id DESC LIMIT 50 OFFSET %s",
        (*values, page * 50),
    )
    return {"items": rows, "page": page, "total": total,"retention":engine.error_retention_policy()}


@app.get("/api/admin/users")
def users(_: Annotated[dict, Depends(admin_user)]):
    return db.all(
        """SELECT id, user_login_id, user_name, user_role, user_email,
                  (deleted_at IS NOT NULL) AS deleted
           FROM tb_user ORDER BY id"""
    )


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, actor: Annotated[dict, Depends(master_user)]):
    target = db.one("SELECT user_login_id, user_role FROM tb_user WHERE id=%s", (user_id,))
    if not target:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")
    if target["user_login_id"] == actor["user_login_id"] and (payload.deleted or payload.user_role != "MASTER"):
        raise HTTPException(400, "현재 MASTER 계정은 비활성화하거나 강등할 수 없습니다.")
    db.execute(
        """WITH updated_user AS (UPDATE tb_user SET user_role=%s,
             deleted_at=CASE WHEN %s THEN COALESCE(deleted_at, to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI:SS.US')) ELSE NULL END,
             updated_at=to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI:SS.US') WHERE id=%s
             RETURNING user_login_id, deleted_at)
           UPDATE tb_upbit_key SET auto_on=false FROM updated_user
           WHERE tb_upbit_key.user_login_id=updated_user.user_login_id AND updated_user.deleted_at IS NOT NULL""",
        (payload.user_role, payload.deleted, user_id),
    )
    return {"ok": True}


@app.get("/api/admin/autos")
def autos(_: Annotated[dict, Depends(admin_user)]):
    return db.all(
        """SELECT u.user_login_id, u.user_name, COALESCE(k.auto_on, false) AS auto_on,
                  (k.id IS NOT NULL) AS key_registered
           FROM tb_user u LEFT JOIN tb_upbit_key k ON k.user_login_id=u.user_login_id
           WHERE u.deleted_at IS NULL ORDER BY u.id"""
    )


@app.put("/api/admin/autos/{login_id}")
def update_auto(login_id: str, payload: AutoUpdate, _: Annotated[dict, Depends(admin_user)]):
    result = db.one("""SELECT k.id FROM tb_upbit_key k JOIN tb_user u ON u.user_login_id=k.user_login_id
        WHERE k.user_login_id=%s AND u.deleted_at IS NULL""", (login_id,))
    if not result:
        raise HTTPException(404, "등록된 Upbit 키가 없습니다.")
    db.execute("UPDATE tb_upbit_key SET auto_on=%s WHERE user_login_id=%s", (payload.auto_on, login_id))
    return {"ok": True}


@app.get("/api/admin/settings")
def settings(_: Annotated[dict, Depends(admin_user)]):
    return db.all(
        """SELECT id, name, expected_high_percentage, expected_low_percentage,
                  highest_price_reference_days, is_volume_check AS volume_check
           FROM deal_settings WHERE deleted_at IS NULL ORDER BY name"""
    )


@app.put("/api/admin/settings/{name}")
def update_setting(name: Literal["stock", "upbit"], payload: SettingUpdate, _: Annotated[dict, Depends(admin_user)]):
    if not db.one("SELECT id FROM deal_settings WHERE name=%s AND deleted_at IS NULL", (name,)):
        raise HTTPException(404, "계산 설정을 찾을 수 없습니다.")
    db.execute(
        """UPDATE deal_settings SET expected_high_percentage=%s, expected_low_percentage=%s,
             highest_price_reference_days=%s, is_volume_check=%s,
             updated_at=to_char(clock_timestamp(), 'YYYY-MM-DD HH24:MI:SS.US')
           WHERE name=%s AND deleted_at IS NULL""",
        (payload.expected_high_percentage, payload.expected_low_percentage,
         payload.highest_price_reference_days, payload.volume_check, name),
    )
    return {"ok": True, "note": "Python 스케줄러가 다음 계산부터 새 설정을 사용합니다."}


# This branch intentionally exposes only the endpoints needed by the Upbit
# MA40 trader. Legacy stock, dividend, AI, mail, user-admin and tunable-strategy
# routes remain out of the public API even when an old database still has their
# tables.
_MA40_API_PATHS = {
    "/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/me",
    "/api/auth/config", "/api/auth/join", "/api/auth/check-id", "/api/profile",
    "/api/dashboard", "/api/orders", "/api/admin/system", "/api/admin/errors",
    "/api/system/public-ip",
    "/api/backtest", "/api/backtest/batch",
    "/api/strategies", "/api/strategies/{market}",
    "/api/upbit/key/status", "/api/upbit/key", "/api/upbit/accounts",
    "/api/upbit/auto", "/api/upbit/auto-markets", "/api/upbit/recommendation-prefs",
    "/api/upbit/recollect", "/api/upbit/auto-orders/reconcile",
    "/api/upbit/orders/market-sell",
}
app.router.routes[:] = [route for route in app.router.routes if not getattr(route, "path", "").startswith("/api/")
                        or route.path in _MA40_API_PATHS]


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"], include_in_schema=False)
@app.api_route("/api", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"], include_in_schema=False)
def missing_api(path: str = ""):
    raise HTTPException(404, "API 경로를 찾을 수 없습니다.")


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"], include_in_schema=False)
    def spa(request: Request, path: str = ""):
        if request.method not in ("GET", "HEAD"):
            raise HTTPException(404, "경로를 찾을 수 없습니다.")
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_relative_to(STATIC_DIR) and candidate.is_file():
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
        if Path(path).suffix:
            raise HTTPException(404, "파일을 찾을 수 없습니다.")
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
