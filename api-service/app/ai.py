"""Owner-scoped AI analysis, separate from the live trading scheduler."""
import base64
import hashlib
import json
import logging
import math
import re
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from psycopg.types.json import Jsonb
from typing import Literal

log = logging.getLogger(__name__)
SETTING_COLUMNS = "expected_high_percentage,expected_low_percentage,highest_price_reference_days,is_volume_check AS volume_check"
SETTING_KEYS = ("expected_high_percentage", "expected_low_percentage", "highest_price_reference_days", "volume_check")
DEFAULT_MODEL = "deepseek-flash"
RUN_TOKEN_BUDGET = 200000
REALIZED_PNL_ORDER_LIMIT = 20


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr | None = None
    model: str = Field(default=DEFAULT_MODEL, pattern=r"^deepseek-[a-z0-9-]{1,40}$")

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        if value is not None and not re.fullmatch(r"[A-Za-z0-9._-]{12,256}", value.get_secret_value()):
            raise ValueError("API 키 형식을 확인해 주세요. 공백 없이 입력해야 합니다.")
        return value


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Literal["stock", "upbit"]
    prompt: str = Field(default="현재 설정과 추천 종목의 근거·위험을 검토하고 설정 후보를 비교해 주세요.", min_length=1, max_length=1500)
    include_account: bool = False
    symbols: list[str] = Field(default_factory=list, max_length=5)
    fee_bps: float = Field(default=5, ge=0, le=100, allow_inf_nan=False)
    slippage_bps: float = Field(default=10, ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_symbols(self):
        pattern = r"KRW-[A-Z0-9]{1,20}" if self.market == "upbit" else r"[0-9]{6}"
        if any(not re.fullmatch(pattern, symbol) for symbol in self.symbols):
            raise ValueError("주식은 6자리 종목 코드, Upbit는 KRW-BTC 형식으로 입력해 주세요.")
        self.symbols = list(dict.fromkeys(self.symbols))
        if self.market == "stock" and "fee_bps" not in self.model_fields_set:
            self.fee_bps = 15
        if not self.prompt.strip():
            raise ValueError("분석 요청을 입력해 주세요.")
        return self


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(pattern=r"^candidate-[1-3]$")
    confirm: Literal[True]


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1500)
    include_portfolio: bool = False

    @field_validator("question")
    @classmethod
    def clean_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("후속 질문을 입력해 주세요.")
        return value


class AutomationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    trigger_mode: Literal["interval", "recommendation_change"] = "interval"
    interval_minutes: int = Field(default=360, ge=60, le=1440)
    auto_apply_settings: bool = False


def settings_dict(row):
    return {key: row[key] for key in SETTING_KEYS}


def account_for_ai(row):
    # avg_buy_price is only KRW-denominated when unit_currency is KRW; for
    # legacy non-KRW-quoted holdings it uses a different scale (e.g. BTC) and
    # must never be compared directly against a KRW daily close by the model.
    unit_currency = row.get("unit_currency")
    is_krw = unit_currency == "KRW"
    return {"currency": row.get("currency"), "balance": row.get("balance"), "locked": row.get("locked"),
            "avg_buy_price": row.get("avg_buy_price") if is_krw else None,
            "avg_buy_price_unit_currency": unit_currency,
            "avg_buy_price_note": None if is_krw else
                "평균매수가가 KRW 기준이 아니어서 제외했습니다. 원화 시세와 직접 비교하지 마세요."}


def key_cipher(secret, user_id):
    if len(secret) < 32:
        raise HTTPException(503, "서버 암호화 설정을 확인해 주세요.")
    # SESSION_SECRET is generated from 32 random bytes by up.sh, not a user password.
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"trading-ai-credentials-v1",
               info=f"deepseek-owner:{user_id}".encode()).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def candidate_verified(candidate):
    metrics = candidate.get("validation") or {}
    return (candidate.get("id") != "current" and metrics.get("days", 0) >= 10
            and metrics.get("trades", 0) > 0)


class AIService:
    def __init__(self, database_provider, engine, calculation_url, session_secret, setting_schema):
        self._database_provider = database_provider
        self.engine, self.calculation_url = engine, calculation_url
        self.session_secret, self.setting_schema = session_secret, setting_schema
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-analysis")
        self.scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._test_times, self._test_lock = {}, threading.Lock()

    @property
    def db(self):
        return self._database_provider()

    @staticmethod
    def today():
        return datetime.now(ZoneInfo("Asia/Seoul")).date()

    def start(self):
        # Single API process deployment: never silently replay a paid call after restart.
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ai_analyses WHERE status IN ('PENDING','RUNNING') FOR UPDATE")
            for row in cursor.fetchall():
                charged = row["reserved_tokens"] if row["status"] == "RUNNING" else 0
                self._settle(cursor, row, "FAILED", charged, None,
                             "서버 재시작으로 중단되었습니다. 실행 중이던 분석의 토큰은 사용량에 보수적으로 반영합니다.")
            cursor.execute("SELECT * FROM ai_conversation_messages WHERE status IN ('PENDING','RUNNING') FOR UPDATE")
            for row in cursor.fetchall():
                charged = row["reserved_tokens"] if row["status"] == "RUNNING" else 0
                self._settle_conversation(cursor, row, "FAILED", charged, None,
                                          "서버 재시작으로 후속 답변이 중단되었습니다. 실행 중이던 요청은 사용량에 보수적으로 반영합니다.")
        self.scheduler.add_job(self.automation_tick, "interval", minutes=1, id="ai-automation",
                               max_instances=1, coalesce=True, misfire_grace_time=30)
        self.scheduler.start()

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.executor.shutdown(wait=False, cancel_futures=True)

    def config(self, user_id):
        config = self.db.one("SELECT model,key_hint FROM ai_credentials WHERE user_id=%s", (user_id,))
        usage = self.db.one("SELECT runs,tokens,reserved_tokens FROM ai_daily_usage WHERE user_id=%s AND usage_date=%s", (user_id, self.today()))
        return {"configured": bool(config), "model": DEFAULT_MODEL, "key_hint": "",
                **(config or {}), "usage_today": usage or {"runs": 0, "tokens": 0, "reserved_tokens": 0},
                "provider_limited": True, "max_tool_calls": 4,
                "max_output_tokens": 2500, "max_run_tokens": RUN_TOKEN_BUDGET}

    def save_config(self, user_id, payload):
        if payload.api_key is not None:
            key = payload.api_key.get_secret_value()
            encrypted = key_cipher(self.session_secret, user_id).encrypt(key.encode()).decode()
            self.db.execute("""INSERT INTO ai_credentials(user_id,encrypted_key,key_hint,model)
                VALUES(%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET encrypted_key=EXCLUDED.encrypted_key,
                key_hint=EXCLUDED.key_hint,model=EXCLUDED.model,updated_at=now()""",
                (user_id, encrypted, "…" + key[-4:], payload.model))
        else:
            result = self.db.one("""UPDATE ai_credentials SET model=%s,updated_at=now()
                WHERE user_id=%s RETURNING user_id""", (payload.model, user_id))
            if not result:
                raise HTTPException(400, "먼저 DeepSeek API 키를 등록해 주세요.")
        return self.config(user_id)

    def credentials(self, user_id):
        row = self.db.one("SELECT * FROM ai_credentials WHERE user_id=%s", (user_id,))
        if not row:
            raise HTTPException(400, "먼저 DeepSeek API 키를 등록해 주세요.")
        try:
            key = key_cipher(self.session_secret, user_id).decrypt(row["encrypted_key"].encode()).decode()
        except (InvalidToken, UnicodeError):
            raise HTTPException(400, "저장된 키를 복호화할 수 없습니다. 서버 비밀키를 확인하거나 API 키를 다시 등록해 주세요.")
        return row, key

    def test_connection(self, user_id):
        with self._test_lock:
            now = time.monotonic()
            if now - self._test_times.get(user_id, -100) < 10:
                raise HTTPException(429, "연결 확인은 10초 후 다시 시도해 주세요.")
            self._test_times[user_id] = now
        config, key = self.credentials(user_id)
        try:
            response = httpx.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {key}"}, timeout=10)
            response.raise_for_status()
            models = [row["id"] for row in response.json().get("data", []) if isinstance(row.get("id"), str)]
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise HTTPException(502, "DeepSeek 연결 확인에 실패했습니다. 키·API 이용 상태를 확인해 주세요.")
        if config["model"] not in models:
            raise HTTPException(400, "연결은 되었으나 선택한 모델을 사용할 수 없습니다. DeepSeek의 현재 모델명을 확인해 주세요.")
        return {"ok": True, "model": config["model"], "available_models": models,
                "message": "연결을 확인했습니다. 분석 토큰을 사용하는 요청은 실행하지 않았습니다."}

    def automation_config(self, user_id):
        row = self.db.one("SELECT * FROM ai_automation_config WHERE user_id=%s", (user_id,))
        return row or {"user_id": user_id, "enabled": False, "trigger_mode": "interval",
                       "interval_minutes": 360, "auto_apply_settings": False,
                       "last_started_at": None, "next_run_at": None, "last_analysis_id": None,
                       "last_error": None}

    def save_automation_config(self, user, payload):
        if payload.enabled:
            if not self.db.one("SELECT 1 FROM ai_credentials WHERE user_id=%s", (user["id"],)):
                raise HTTPException(400, "먼저 DeepSeek API 키를 등록해 주세요.")
            if not self.db.one("SELECT 1 FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],)):
                raise HTTPException(400, "먼저 Upbit API 키를 등록해 주세요.")
        self.db.execute("""INSERT INTO ai_automation_config(user_id,enabled,trigger_mode,interval_minutes,
            auto_apply_settings,next_run_at,updated_at)
            VALUES(%s,%s,%s,%s,%s,CASE WHEN %s THEN now() ELSE NULL END,now())
            ON CONFLICT(user_id) DO UPDATE SET enabled=EXCLUDED.enabled,
              trigger_mode=EXCLUDED.trigger_mode,interval_minutes=EXCLUDED.interval_minutes,
              auto_apply_settings=EXCLUDED.auto_apply_settings,
              next_run_at=CASE WHEN EXCLUDED.enabled THEN now() ELSE NULL END,
              last_fingerprint=CASE WHEN EXCLUDED.enabled THEN NULL ELSE ai_automation_config.last_fingerprint END,
              last_error=NULL,updated_at=now()""",
            (user["id"], payload.enabled, payload.trigger_mode, payload.interval_minutes,
             payload.auto_apply_settings, payload.enabled))
        return self.automation_config(user["id"])

    def _automation_fingerprint(self):
        settings = self.db.one(f"SELECT {SETTING_COLUMNS} FROM deal_settings WHERE name='upbit' AND deleted_at IS NULL")
        recommendations = self.db.all("""SELECT code,renewal_cnt,temp_price,minimum_selling_price,
            expected_selling_price,pricing_reference_date FROM upbit WHERE deleted_at IS NULL
            ORDER BY code""")
        raw = json.dumps({"settings": settings, "recommendations": recommendations}, ensure_ascii=False,
                         sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    def _launch_automation(self, config, *, force=False):
        fingerprint = self._automation_fingerprint()
        if (not force and config["trigger_mode"] == "recommendation_change"
                and config.get("last_fingerprint") == fingerprint):
            return None
        user = self.db.one("""SELECT id,user_login_id,user_role FROM tb_user
            WHERE id=%s AND deleted_at IS NULL AND user_role='MASTER'""", (config["user_id"],))
        if not user:
            raise RuntimeError("자동 AI 검토를 실행할 MASTER 사용자를 찾을 수 없습니다.")
        payload = AnalysisRequest(market="upbit", include_account=True, symbols=[], fee_bps=5,
            slippage_bps=10, prompt=("현재 보유 계좌, 기존 추천 이력, 활성 추천, 계산 설정과 완료 일봉을 함께 검토하세요. "
            "각 보유 종목을 SELL/HOLD/WATCH로 하나만 명확히 분류하고 핵심 근거를 짧게 제시하세요. "
            "설정 후보는 목표 상승률, 허용 하락률, 분석 기간, 거래량 조건을 모두 제시하고 과거 검증 가능한 안만 제안하세요."))
        result = self.enqueue(user, payload, automation_run=True)
        self.db.execute("""UPDATE ai_automation_config SET last_fingerprint=%s,last_started_at=now(),
            next_run_at=now()+(interval_minutes*interval '1 minute'),last_analysis_id=%s,last_error=NULL,
            updated_at=now() WHERE user_id=%s""", (fingerprint, result["id"], config["user_id"]))
        return result

    def automation_tick(self):
        configs = self.db.all("""SELECT c.* FROM ai_automation_config c
            JOIN ai_credentials a ON a.user_id=c.user_id WHERE c.enabled=true
              AND (c.trigger_mode='recommendation_change' OR c.next_run_at IS NULL OR c.next_run_at<=now())""")
        for config in configs:
            try:
                self._launch_automation(config)
            except HTTPException as error:
                if error.status_code not in (409, 429):
                    self.db.execute("UPDATE ai_automation_config SET last_error=%s,updated_at=now() WHERE user_id=%s",
                                    (str(error.detail)[:500], config["user_id"]))
            except Exception as error:
                log.exception("Scheduled AI review failed for user %s", config["user_id"])
                self.db.execute("UPDATE ai_automation_config SET last_error=%s,updated_at=now() WHERE user_id=%s",
                                (str(error)[:500] or type(error).__name__, config["user_id"]))

    def run_automation_now(self, user):
        config = self.automation_config(user["id"])
        if not config.get("enabled"):
            raise HTTPException(409, "AI 자동 검토를 먼저 켜 주세요.")
        result = self._launch_automation(config, force=True)
        if not result:
            raise HTTPException(409, "자동 검토를 시작하지 못했습니다.")
        return result

    def enqueue(self, user, payload, automation_run=False):
        user_id, today = user["id"], self.today()
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('trading-ai-queue'))")
            cursor.execute("SELECT * FROM ai_credentials WHERE user_id=%s", (user_id,))
            config = cursor.fetchone()
            if not config:
                raise HTTPException(400, "먼저 DeepSeek API 키를 등록해 주세요.")
            cursor.execute("SELECT count(*) AS count FROM ai_analyses WHERE status IN ('PENDING','RUNNING')")
            active = cursor.fetchone()["count"]
            cursor.execute("SELECT count(*) AS count FROM ai_conversation_messages WHERE status IN ('PENDING','RUNNING')")
            if active + cursor.fetchone()["count"] >= 4:
                raise HTTPException(429, "분석 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요.")
            cursor.execute("SELECT id FROM ai_analyses WHERE user_id=%s AND status IN ('PENDING','RUNNING')", (user_id,))
            if cursor.fetchone():
                raise HTTPException(409, "이미 진행 중인 분석이 있습니다.")
            cursor.execute("SELECT id FROM ai_conversation_messages WHERE user_id=%s AND status IN ('PENDING','RUNNING')", (user_id,))
            if cursor.fetchone():
                raise HTTPException(409, "진행 중인 AI 후속 답변을 기다려 주세요.")
            cursor.execute(f"SELECT {SETTING_COLUMNS} FROM deal_settings WHERE name=%s AND deleted_at IS NULL", (payload.market,))
            current = cursor.fetchone()
            if not current:
                raise HTTPException(404, "분석할 현재 설정이 없습니다.")
            snapshot = self.setting_schema.model_validate(current).model_dump()
            cursor.execute("INSERT INTO ai_daily_usage(user_id,usage_date) VALUES(%s,%s) ON CONFLICT DO NOTHING", (user_id, today))
            cursor.execute("SELECT * FROM ai_daily_usage WHERE user_id=%s AND usage_date=%s FOR UPDATE", (user_id, today))
            usage = cursor.fetchone()
            budget = RUN_TOKEN_BUDGET
            cursor.execute("UPDATE ai_daily_usage SET runs=runs+1,reserved_tokens=reserved_tokens+%s WHERE user_id=%s AND usage_date=%s", (budget, user_id, today))
            cursor.execute("""INSERT INTO ai_analyses(user_id,market,status,prompt,include_account,request_payload,
                settings_snapshot,model,reserved_tokens,usage_date,automation_run)
                VALUES(%s,%s,'PENDING',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,status""",
                (user_id, payload.market, payload.prompt, payload.include_account, Jsonb(payload.model_dump()),
                 Jsonb(snapshot), config["model"], budget, today, automation_run))
            result = cursor.fetchone()
        try:
            self.executor.submit(self._run, result["id"])
        except RuntimeError:
            self._finish(result["id"], "FAILED", 0, None, "서버가 종료 중입니다. 재시작 후 다시 시도해 주세요.")
            raise HTTPException(503, "서버가 종료 중입니다. 잠시 후 다시 시도해 주세요.")
        return result

    def _context(self, job, user):
        market = job["market"]
        recommendations = self.db.all(f"""SELECT code,name,temp_price,expected_selling_price,minimum_selling_price,
            renewal_cnt,updated_at FROM {market} WHERE deleted_at IS NULL ORDER BY renewal_cnt DESC,id DESC LIMIT 20""")
        recommendation_history = self.db.all(f"""SELECT code,name,temp_price,expected_selling_price,
            minimum_selling_price,renewal_cnt,created_at,updated_at,deleted_at
            FROM {market} ORDER BY id DESC LIMIT 60""")
        context = {"settings": job["settings_snapshot"], "recommendations": recommendations,
                   "recommendation_history": recommendation_history,
                   "snapshot_at": datetime.now(timezone.utc).isoformat()}
        context["error_counts"] = self.db.all("""SELECT source,error_type,count(*) AS count FROM trade_error_log
            WHERE created_at::timestamp > now()-interval '24 hours' GROUP BY source,error_type ORDER BY count(*) DESC LIMIT 10""")
        if job["include_account"] and market == "upbit":
            key = self.db.one("SELECT access_key,secret_key FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
            if key:
                # Do not call /accounts route: its authentication failure changes auto_on.
                try:
                    accounts = self.engine.private_upbit("GET", "/v1/accounts", key["access_key"], key["secret_key"])
                    context["account"] = [account_for_ai(row) for row in accounts[:100]]
                except (httpx.HTTPError, ValueError, TypeError):
                    context["account_warning"] = "계좌 조회에 실패하여 계좌 요약은 포함하지 않았습니다. 자동매매 설정은 변경하지 않았습니다."
            else:
                context["account_warning"] = "등록된 Upbit 키가 없어 계좌 요약은 포함하지 않았습니다."
        # psycopg may return Decimal/datetime values. Convert them before the
        # bounded JSON-size check and before anything is sent to the provider.
        return json.loads(json.dumps(context, ensure_ascii=False, default=str))

    def _run(self, analysis_id):
        job = self.db.one("UPDATE ai_analyses SET status='RUNNING' WHERE id=%s AND status='PENDING' RETURNING *", (analysis_id,))
        if not job:
            return
        used, request_started = 0, False
        try:
            from app.ai_engine import analyze, AIAnalysisError
            user = self.db.one("SELECT id,user_login_id FROM tb_user WHERE id=%s AND deleted_at IS NULL AND user_role IN ('ADMIN','MASTER')", (job["user_id"],))
            if not user:
                raise HTTPException(403, "분석 권한이 없어 작업을 중단했습니다.")
            _, key = self.credentials(job["user_id"])
            context = self._context(job, user)
            payload = AnalysisRequest.model_validate(job["request_payload"])
            account_symbols = []
            if job["market"] == "upbit":
                for account in context.get("account", []):
                    try:
                        if account.get("currency") != "KRW" and float(account.get("balance") or 0) + float(account.get("locked") or 0) > 0:
                            account_symbols.append(f"KRW-{account['currency']}")
                    except (TypeError, ValueError):
                        continue
            requested = payload.symbols or [r["code"] for r in context["recommendations"][:3]]
            symbols = list(dict.fromkeys(account_symbols + requested))[:5]
            if len(set(account_symbols + requested)) > 5:
                context["universe_warning"] = "보유·선택 종목이 5개를 넘어 보유 종목 우선 최대 5개만 분석했습니다."
            if not symbols:
                symbols = ["KRW-BTC", "KRW-ETH", "KRW-XRP"] if job["market"] == "upbit" else ["005930", "000660", "035420"]
                context["universe_warning"] = "현재 추천 목록이 없어 기본 예시 종목으로 분석합니다. 전체 시장을 대표하지 않습니다."
            request_started = True
            result = analyze(api_key=key, model=job["model"], market=job["market"], prompt=payload.prompt,
                             context=context, symbols=symbols, fee_bps=payload.fee_bps, slippage_bps=payload.slippage_bps,
                             remaining_tokens=job["reserved_tokens"], calculation_url=self.calculation_url)
            used = max(0, int(result.get("usage_tokens", 0)))
            for candidate in result.get("candidates", []):
                candidate["settings"] = self.setting_schema.model_validate(candidate["settings"]).model_dump()
                candidate["can_apply"] = candidate_verified(candidate)
            result.setdefault("warnings", []).extend(context[k] for k in ("account_warning", "universe_warning") if k in context)
            # Defense in depth: never persist even an accidentally echoed provider credential.
            result = json.loads(json.dumps(result, ensure_ascii=False, default=str).replace(key, "[REDACTED]"))
            self._finish(analysis_id, "COMPLETED", used, result, None)
            if job.get("automation_run"):
                self._auto_apply_verified_settings(analysis_id, result)
        except Exception as error:
            from app.ai_engine import AIAnalysisError
            if isinstance(error, AIAnalysisError):
                used = max(0, int(getattr(error, "consumed_tokens", 0)))
                message = str(error)[:500]
            elif isinstance(error, HTTPException):
                message = str(error.detail)
            else:
                used = job["reserved_tokens"] if request_started else 0
                message = "AI 분석을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요. 기존 자동매매에는 영향이 없습니다."
            self._finish(analysis_id, "FAILED", used, None, message)

    def _auto_apply_verified_settings(self, analysis_id, result):
        candidates = result.get("candidates", []) if isinstance(result, dict) else []
        baseline = next((item for item in candidates if item.get("id") in {"current", "baseline"}), None)
        baseline_validation = (baseline or {}).get("validation") or {}
        try:
            baseline_return = float(baseline_validation["return_pct"])
            baseline_drawdown = float(baseline_validation["max_drawdown_pct"])
        except (KeyError, TypeError, ValueError):
            self.db.execute("UPDATE ai_analyses SET automation_note=%s WHERE id=%s",
                            ("기존 설정의 검증 지표가 없어 자동 적용하지 않았습니다.", analysis_id))
            return
        eligible = []
        for candidate in candidates:
            metrics = candidate.get("validation") or {}
            try:
                candidate_return = float(metrics["return_pct"])
                candidate_drawdown = float(metrics["max_drawdown_pct"])
                days, trades = int(metrics["days"]), int(metrics["trades"])
            except (KeyError, TypeError, ValueError):
                continue
            if (candidate.get("id") not in {"current", "baseline"} and days >= 20 and trades >= 3
                    and candidate_return > baseline_return and candidate_drawdown >= baseline_drawdown - 2):
                eligible.append((candidate_return, candidate))
        if not eligible:
            self.db.execute("UPDATE ai_analyses SET automation_note=%s WHERE id=%s",
                            ("검증 20일·청산 3건·기존 대비 수익 개선·낙폭 악화 2%p 이내 조건을 통과한 설정이 없어 유지했습니다.", analysis_id))
            return
        selected = max(eligible, key=lambda item: item[0])[1]
        proposed = self.setting_schema.model_validate(selected["settings"]).model_dump()
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT a.*,c.auto_apply_settings FROM ai_analyses a
                JOIN ai_automation_config c ON c.user_id=a.user_id
                WHERE a.id=%s FOR UPDATE""", (analysis_id,))
            analysis = cursor.fetchone()
            if not analysis or not analysis["auto_apply_settings"]:
                cursor.execute("UPDATE ai_analyses SET automation_note=%s WHERE id=%s",
                               ("자동 설정 적용이 꺼져 있어 분석 결과만 저장했습니다.", analysis_id))
                return
            cursor.execute(f"SELECT {SETTING_COLUMNS} FROM deal_settings WHERE name=%s AND deleted_at IS NULL FOR UPDATE",
                           (analysis["market"],))
            current = cursor.fetchone()
            if not current or settings_dict(current) != analysis["settings_snapshot"]:
                cursor.execute("UPDATE ai_analyses SET automation_note=%s WHERE id=%s",
                               ("분석 중 설정이 변경되어 자동 적용하지 않았습니다.", analysis_id))
                return
            cursor.execute("""UPDATE deal_settings SET expected_high_percentage=%s,expected_low_percentage=%s,
                highest_price_reference_days=%s,is_volume_check=%s,
                updated_at=to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US')
                WHERE name=%s AND deleted_at IS NULL""", (*[proposed[key] for key in SETTING_KEYS], analysis["market"]))
            cursor.execute("""UPDATE ai_analyses SET applied_candidate_id=%s,applied_at=now(),applied_by=%s,
                automation_note=%s WHERE id=%s""", (selected["id"], analysis["user_id"],
                "강화된 과거 검증 기준을 통과한 설정을 자동 적용했습니다. AI가 주문을 직접 실행하지는 않았습니다.", analysis_id))

    @staticmethod
    def _settle(cursor, row, status, used, result, error_message):
        cursor.execute("""UPDATE ai_daily_usage SET tokens=tokens+%s,reserved_tokens=GREATEST(0,reserved_tokens-%s)
            WHERE user_id=%s AND usage_date=%s""", (used, row["reserved_tokens"], row["user_id"], row["usage_date"]))
        cursor.execute("""UPDATE ai_analyses SET status=%s,usage_tokens=%s,reserved_tokens=0,result=%s,
            error_message=%s,completed_at=now() WHERE id=%s""", (status, used, Jsonb(result) if result is not None else None, error_message, row["id"]))

    def _finish(self, analysis_id, status, used, result, error_message):
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ai_analyses WHERE id=%s FOR UPDATE", (analysis_id,))
            row = cursor.fetchone()
            if row and row["status"] in {"PENDING", "RUNNING"}:
                self._settle(cursor, row, status, used, result, error_message)

    def history(self, user_id, page):
        total = self.db.one("SELECT count(*) AS count FROM ai_analyses WHERE user_id=%s", (user_id,))["count"]
        items = self.db.all("""SELECT id,market,status,prompt,created_at,completed_at,error_message,usage_tokens,automation_run
            FROM ai_analyses WHERE user_id=%s ORDER BY id DESC LIMIT 10 OFFSET %s""", (user_id, page * 10))
        return {"items": items, "total": total, "page": page, "page_size": 10}

    def recommendations(self, market):
        return self.db.all(f"""SELECT code,name,renewal_cnt FROM {market}
            WHERE deleted_at IS NULL ORDER BY renewal_cnt DESC,id DESC LIMIT 12""")

    def detail(self, user_id, analysis_id):
        row = self.db.one("""SELECT id,market,status,prompt,include_account,settings_snapshot,result,error_message,
            model,usage_tokens,created_at,completed_at,applied_candidate_id,applied_at,automation_run,automation_note
            FROM ai_analyses WHERE id=%s AND user_id=%s""", (analysis_id, user_id))
        if not row:
            raise HTTPException(404, "분석 결과를 찾을 수 없습니다.")
        row["conversations"] = self.db.all("""SELECT id,status,question,answer,research,error_message,usage_tokens,
            include_portfolio,created_at,completed_at FROM ai_conversation_messages
            WHERE analysis_id=%s AND user_id=%s ORDER BY id""", (analysis_id, user_id))
        return row

    def delete_analysis(self, user_id, analysis_id):
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status,applied_candidate_id FROM ai_analyses WHERE id=%s AND user_id=%s FOR UPDATE",
                           (analysis_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, "대화를 찾을 수 없습니다.")
            if row["status"] in {"PENDING", "RUNNING"}:
                raise HTTPException(409, "진행 중인 대화는 삭제할 수 없습니다.")
            if row["applied_candidate_id"]:
                raise HTTPException(409, "실제 설정을 적용한 분석은 감사 기록 보존을 위해 삭제할 수 없습니다.")
            cursor.execute("DELETE FROM ai_analyses WHERE id=%s AND user_id=%s", (analysis_id, user_id))

    def enqueue_conversation(self, user_id, analysis_id, payload):
        today = self.today()
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('trading-ai-queue'))")
            cursor.execute("SELECT * FROM ai_credentials WHERE user_id=%s", (user_id,))
            config = cursor.fetchone()
            if not config:
                raise HTTPException(400, "먼저 DeepSeek API 키를 등록해 주세요.")
            cursor.execute("SELECT id,status FROM ai_analyses WHERE id=%s AND user_id=%s", (analysis_id, user_id))
            analysis = cursor.fetchone()
            if not analysis:
                raise HTTPException(404, "분석 결과를 찾을 수 없습니다.")
            if analysis["status"] != "COMPLETED":
                raise HTTPException(409, "완료된 분석에서만 후속 질문을 할 수 있습니다.")
            cursor.execute("SELECT 1 FROM ai_analyses WHERE user_id=%s AND status IN ('PENDING','RUNNING')", (user_id,))
            if cursor.fetchone():
                raise HTTPException(409, "진행 중인 새 분석을 기다려 주세요.")
            cursor.execute("SELECT count(*) AS count FROM ai_analyses WHERE status IN ('PENDING','RUNNING')")
            active = cursor.fetchone()["count"]
            cursor.execute("SELECT count(*) AS count FROM ai_conversation_messages WHERE status IN ('PENDING','RUNNING')")
            if active + cursor.fetchone()["count"] >= 4:
                raise HTTPException(429, "AI 요청 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요.")
            cursor.execute("""SELECT 1 FROM ai_conversation_messages
                WHERE user_id=%s AND status IN ('PENDING','RUNNING')""", (user_id,))
            if cursor.fetchone():
                raise HTTPException(409, "이미 진행 중인 후속 답변이 있습니다.")
            cursor.execute("INSERT INTO ai_daily_usage(user_id,usage_date) VALUES(%s,%s) ON CONFLICT DO NOTHING", (user_id, today))
            cursor.execute("SELECT * FROM ai_daily_usage WHERE user_id=%s AND usage_date=%s FOR UPDATE", (user_id, today))
            usage = cursor.fetchone()
            budget = RUN_TOKEN_BUDGET
            cursor.execute("UPDATE ai_daily_usage SET runs=runs+1,reserved_tokens=reserved_tokens+%s WHERE user_id=%s AND usage_date=%s",
                           (budget, user_id, today))
            cursor.execute("""INSERT INTO ai_conversation_messages(analysis_id,user_id,status,question,
                include_portfolio,reserved_tokens,usage_date)
                VALUES(%s,%s,'PENDING',%s,%s,%s,%s) RETURNING id,status""",
                           (analysis_id, user_id, payload.question, payload.include_portfolio, budget, today))
            result = cursor.fetchone()
        try:
            self.executor.submit(self._run_conversation, result["id"])
        except RuntimeError:
            self._finish_conversation(result["id"], "FAILED", 0, None, "서버가 종료 중입니다. 잠시 후 다시 시도해 주세요.")
            raise HTTPException(503, "서버가 종료 중입니다. 잠시 후 다시 시도해 주세요.")
        return result

    def _realized_pnl_summary(self, key_row, orders):
        # Locally stored history has no proceeds for market sell orders
        # (Upbit leaves `price` empty for them), so this fetches each
        # completed order's actual trade fills instead of trusting local
        # fields. Bounded to the most recent orders to fit the analysis
        # time budget; earlier orders are simply out of window, not errors.
        done = [order for order in orders if order.get("state") == "done" and order.get("market") and order.get("uuid")]
        recent = done[:REALIZED_PNL_ORDER_LIMIT]
        fills, unavailable_markets = [], set()
        for order in reversed(recent):  # oldest-first so FIFO matching sees buys before their sells
            try:
                trades = self.engine.order_fills(key_row["access_key"], key_row["secret_key"], order["uuid"])
            except (httpx.HTTPError, ValueError, TypeError):
                unavailable_markets.add(order["market"])
                continue
            volume = sum(float(trade.get("volume") or 0) for trade in trades if isinstance(trade, dict))
            funds = sum(float(trade.get("funds") or 0) for trade in trades if isinstance(trade, dict))
            if volume <= 0 or not math.isfinite(volume) or not math.isfinite(funds):
                continue
            fills.append({"market": order["market"], "side": order.get("side"), "volume": volume,
                          "funds": funds, "fee": float(order.get("paid_fee") or 0)})
        lots, summary = defaultdict(deque), {}
        for fill in fills:
            stats = summary.setdefault(fill["market"], {"realized_krw": 0.0, "matched_volume": 0.0,
                                                         "closed_sell_fills": 0, "unmatched_sell_volume": 0.0})
            if fill["side"] == "bid":
                lots[fill["market"]].append([fill["volume"], (fill["funds"] + fill["fee"]) / fill["volume"]])
            elif fill["side"] == "ask":
                unit_proceeds, remaining = (fill["funds"] - fill["fee"]) / fill["volume"], fill["volume"]
                while remaining > 1e-9 and lots[fill["market"]]:
                    lot = lots[fill["market"]][0]
                    matched = min(remaining, lot[0])
                    stats["realized_krw"] += matched * (unit_proceeds - lot[1])
                    stats["matched_volume"] += matched
                    lot[0] -= matched
                    remaining -= matched
                    if lot[0] <= 1e-9:
                        lots[fill["market"]].popleft()
                stats["unmatched_sell_volume"] += remaining
                stats["closed_sell_fills"] += 1
        return {"per_market": {market: {**stats, "realized_krw": round(stats["realized_krw"], 2)}
                               for market, stats in summary.items()},
                "orders_examined": len(recent), "orders_unavailable": sorted(unavailable_markets),
                "notice": (f"최근 체결 완료 주문 최대 {REALIZED_PNL_ORDER_LIMIT}건의 실제 체결 내역(Upbit 조회)으로 계산한 "
                          "부분 실현손익입니다. 이 범위 이전에 매수한 물량의 원가는 알 수 없어 그만큼 매도된 수량은 "
                          "unmatched_sell_volume으로 표시하며, 세금·미실현 평가손익은 포함하지 않습니다.")}

    def _run_conversation(self, message_id):
        row = self.db.one("UPDATE ai_conversation_messages SET status='RUNNING' WHERE id=%s AND status='PENDING' RETURNING *", (message_id,))
        if not row:
            return
        used, request_started = 0, False
        try:
            from app.ai_engine import AIAnalysisError, continue_analysis
            analysis = self.db.one("""SELECT * FROM ai_analyses
                WHERE id=%s AND user_id=%s AND status='COMPLETED'""", (row["analysis_id"], row["user_id"]))
            if not analysis:
                raise HTTPException(409, "기존 분석을 확인할 수 없습니다.")
            _, key = self.credentials(row["user_id"])
            request_payload = AnalysisRequest.model_validate(analysis["request_payload"])
            symbols = request_payload.symbols or [item.get("code") for item in (analysis["result"] or {}).get("data_sources", [])
                                                   if isinstance(item, dict) and item.get("code")]
            symbols = list(dict.fromkeys(symbols))[:5]
            if not symbols:
                symbols = ["KRW-BTC"] if analysis["market"] == "upbit" else ["005930"]
            prior_rows = self.db.all("""SELECT question,answer FROM ai_conversation_messages
                WHERE analysis_id=%s AND user_id=%s AND status='COMPLETED' AND id<%s ORDER BY id DESC LIMIT 50""",
                                (analysis["id"], row["user_id"], row["id"]))
            prior, prior_bytes = [], 0
            for item in prior_rows:
                item_bytes = len(json.dumps(item, ensure_ascii=False, default=str).encode("utf-8"))
                if prior_bytes + item_bytes > 140000:
                    break
                prior.append(item)
                prior_bytes += item_bytes
            prior.reverse()
            original = {"question": analysis["prompt"], "report": (analysis["result"] or {}).get("report"),
                        "candidates": (analysis["result"] or {}).get("candidates", []),
                        "warnings": (analysis["result"] or {}).get("warnings", []),
                        "dataset": (analysis["result"] or {}).get("dataset"),
                        "request": {"fee_bps": request_payload.fee_bps, "slippage_bps": request_payload.slippage_bps}}
            label_table = "upbit_history_label" if analysis["market"] == "upbit" else "stock_history_label"
            catalog = self.db.all(f"""SELECT code,name FROM {label_table}
                WHERE deleted_at IS NULL ORDER BY name,code LIMIT 5000""")
            portfolio = None
            if row.get("include_portfolio"):
                if analysis["market"] != "upbit" or not analysis.get("include_account"):
                    raise HTTPException(409, "계좌 정보 포함에 동의한 Upbit 분석에서만 계좌·주문 요약을 사용할 수 있습니다.")
                owner = self.db.one("SELECT user_login_id FROM tb_user WHERE id=%s AND deleted_at IS NULL", (row["user_id"],))
                key_row = self.db.one("SELECT access_key,secret_key FROM tb_upbit_key WHERE user_login_id=%s", (owner["user_login_id"],)) if owner else None
                if not key_row:
                    raise HTTPException(409, "현재 Upbit 계좌 정보를 확인할 수 없습니다.")
                accounts = self.engine.private_upbit("GET", "/v1/accounts", key_row["access_key"], key_row["secret_key"])
                orders = self.db.all("""SELECT uuid,market,side,ord_type,state,price,volume,executed_volume,
                    paid_fee,trades_count,created_at FROM upbit_order_history
                    WHERE login_id=%s ORDER BY id DESC LIMIT 100""", (owner["user_login_id"],))
                try:
                    realized_pnl = self._realized_pnl_summary(key_row, orders)
                except (httpx.HTTPError, ValueError, TypeError):
                    realized_pnl = {"per_market": {}, "notice": "실현손익 계산에 필요한 체결 내역을 Upbit에서 조회하지 못했습니다."}
                recent_orders = [{key: value for key, value in order.items() if key != "uuid"} for order in orders]
                portfolio = {"accounts": [account_for_ai(item) for item in accounts[:100]],
                    "recent_orders": recent_orders, "order_limit": 100, "realized_pnl": realized_pnl,
                    "notice": "현재 잔고와 앱에 저장된 최근 주문 기록입니다. 주문 UUID와 API 키는 포함하지 않습니다."}
                portfolio = json.loads(json.dumps(portfolio, ensure_ascii=False, default=str))
            request_started = True
            result = continue_analysis(api_key=key, model=analysis["model"], market=analysis["market"],
                                       question=row["question"], analysis_context=original,
                                       prior_messages=prior, symbols=symbols, remaining_tokens=row["reserved_tokens"],
                                       calculation_url=self.calculation_url, instrument_catalog=catalog,
                                       portfolio_context=portfolio)
            used = max(0, int(result.get("usage_tokens", 0)))
            result = json.loads(json.dumps(result, ensure_ascii=False, default=str).replace(key, "[REDACTED]"))
            self._finish_conversation(message_id, "COMPLETED", used, result, None)
        except Exception as error:
            from app.ai_engine import AIAnalysisError
            if isinstance(error, AIAnalysisError):
                used, message = max(0, int(getattr(error, "consumed_tokens", 0))), str(error)[:500]
            elif isinstance(error, HTTPException):
                message = str(error.detail)
            else:
                used = row["reserved_tokens"] if request_started else 0
                message = "AI 후속 답변을 완료하지 못했습니다. 기존 분석과 자동매매에는 영향이 없습니다."
            self._finish_conversation(message_id, "FAILED", used, None, message)

    @staticmethod
    def _settle_conversation(cursor, row, status, used, result, error_message):
        cursor.execute("""UPDATE ai_daily_usage SET tokens=tokens+%s,reserved_tokens=GREATEST(0,reserved_tokens-%s)
            WHERE user_id=%s AND usage_date=%s""", (used, row["reserved_tokens"], row["user_id"], row["usage_date"]))
        cursor.execute("""UPDATE ai_conversation_messages SET status=%s,usage_tokens=%s,reserved_tokens=0,
            answer=%s,research=%s,error_message=%s,completed_at=now() WHERE id=%s""",
                       (status, used, result.get("answer") if result else None, Jsonb(result) if result else None,
                        error_message, row["id"]))

    def _finish_conversation(self, message_id, status, used, result, error_message):
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ai_conversation_messages WHERE id=%s FOR UPDATE", (message_id,))
            row = cursor.fetchone()
            if row and row["status"] in {"PENDING", "RUNNING"}:
                self._settle_conversation(cursor, row, status, used, result, error_message)

    def apply(self, user_id, analysis_id, payload):
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ai_analyses WHERE id=%s AND user_id=%s FOR UPDATE", (analysis_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, "분석 결과를 찾을 수 없습니다.")
            if row["status"] != "COMPLETED" or row["applied_candidate_id"]:
                raise HTTPException(409, "완료된 미적용 분석만 적용할 수 있습니다.")
            if row["created_at"] < datetime.now(timezone.utc) - timedelta(days=7):
                raise HTTPException(409, "분석 후 7일이 지났습니다. 최신 데이터로 다시 분석해 주세요.")
            candidate = next((c for c in (row["result"] or {}).get("candidates", []) if c.get("id") == payload.candidate_id), None)
            if not candidate or not candidate_verified(candidate):
                raise HTTPException(400, "검증 기간 10일 이상·청산 거래 1건 이상인 설정 후보만 적용할 수 있습니다. 이는 수익성을 보장하지 않습니다.")
            proposed = self.setting_schema.model_validate(candidate["settings"]).model_dump()
            cursor.execute(f"SELECT {SETTING_COLUMNS} FROM deal_settings WHERE name=%s AND deleted_at IS NULL FOR UPDATE", (row["market"],))
            current = cursor.fetchone()
            if not current or settings_dict(current) != row["settings_snapshot"]:
                raise HTTPException(409, "분석 이후 현재 설정이 바뀌었습니다. 다시 분석한 후 적용해 주세요.")
            cursor.execute("""UPDATE deal_settings SET expected_high_percentage=%s,expected_low_percentage=%s,
                highest_price_reference_days=%s,is_volume_check=%s,updated_at=to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US')
                WHERE name=%s AND deleted_at IS NULL""", (*[proposed[k] for k in SETTING_KEYS], row["market"]))
            cursor.execute("UPDATE ai_analyses SET applied_candidate_id=%s,applied_at=now(),applied_by=%s WHERE id=%s", (payload.candidate_id, user_id, analysis_id))
        return {"ok": True, "settings": proposed, "note": "승인한 설정을 저장했습니다. 다음 계산부터 적용되며 지금 주문을 실행하지는 않습니다."}


def create_router(service, admin_dependency, master_dependency):
    router = APIRouter(prefix="/api/admin/ai", tags=["AI analysis"])

    @router.get("/config")
    def config(user: dict = Depends(admin_dependency)):
        return service.config(user["id"])

    @router.put("/config")
    def save_config(payload: ConfigUpdate, user: dict = Depends(admin_dependency)):
        return service.save_config(user["id"], payload)

    @router.delete("/config", status_code=204)
    def remove_config(user: dict = Depends(admin_dependency)):
        service.db.execute("DELETE FROM ai_credentials WHERE user_id=%s", (user["id"],))

    @router.post("/config/test")
    def test_config(user: dict = Depends(admin_dependency)):
        return service.test_connection(user["id"])

    @router.get("/automation")
    def automation(user: dict = Depends(master_dependency)):
        return service.automation_config(user["id"])

    @router.put("/automation")
    def save_automation(payload: AutomationUpdate, user: dict = Depends(master_dependency)):
        return service.save_automation_config(user, payload)

    @router.post("/automation/run", status_code=202)
    def run_automation(user: dict = Depends(master_dependency)):
        return service.run_automation_now(user)

    @router.get("/analyses")
    def analyses(page: int = Query(default=0, ge=0, le=100000), user: dict = Depends(admin_dependency)):
        return service.history(user["id"], page)

    @router.get("/recommendations/{market}")
    def recommendation_choices(market: Literal["stock", "upbit"],
                               _: dict = Depends(admin_dependency)):
        return service.recommendations(market)

    @router.get("/analyses/{analysis_id}")
    def analysis(analysis_id: int, user: dict = Depends(admin_dependency)):
        return service.detail(user["id"], analysis_id)

    @router.delete("/analyses/{analysis_id}", status_code=204)
    def delete_analysis(analysis_id: int, user: dict = Depends(admin_dependency)):
        service.delete_analysis(user["id"], analysis_id)

    @router.post("/analyses", status_code=202)
    def start_analysis(payload: AnalysisRequest, user: dict = Depends(admin_dependency)):
        return service.enqueue(user, payload)

    @router.post("/analyses/{analysis_id}/apply")
    def apply_analysis(analysis_id: int, payload: ApplyRequest, user: dict = Depends(master_dependency)):
        return service.apply(user["id"], analysis_id, payload)

    @router.post("/analyses/{analysis_id}/messages", status_code=202)
    def continue_conversation(analysis_id: int, payload: ConversationRequest,
                              user: dict = Depends(admin_dependency)):
        return service.enqueue_conversation(user["id"], analysis_id, payload)

    return router
