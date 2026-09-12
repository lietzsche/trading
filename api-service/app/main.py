import os
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Literal

import bcrypt
import httpx
import psycopg
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field, field_validator, model_validator
from psycopg.rows import dict_row
from app.trading import TradingEngine


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bion_user@postgres:5432/postgres")
CALCULATION_SERVICE_URL = os.environ.get("CALCULATION_SERVICE_URL", "http://calculation-service:8000")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
SESSION_MAX_AGE = 60 * 60 * 12
STARTED_AT = time.monotonic()
TRADING_ENABLED = os.environ.get("TRADING_EXECUTION_ENABLED", "false").lower() == "true"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class LoginRequest(BaseModel):
    login_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserUpdate(BaseModel):
    user_role: Literal["USER", "ADMIN", "MASTER"]
    deleted: bool = False


class AutoUpdate(BaseModel):
    auto_on: bool


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

    def executemany(self, query: str, params):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.executemany(query, params)


db = Database()
engine = TradingEngine(db, CALCULATION_SERVICE_URL, TRADING_ENABLED)


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine.start()
    yield
    engine.stop()


app = FastAPI(title="Trading API", version="2.0.0", lifespan=lifespan)


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
        login_id = serializer().loads(session, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "세션이 만료되었습니다.")
    user = db.one(
        """SELECT id, user_login_id, user_name, user_role, user_email, user_phone
           FROM tb_user WHERE user_login_id=%s AND deleted_at IS NULL""",
        (login_id,),
    )
    if not user:
        raise HTTPException(401, "사용자를 찾을 수 없습니다.")
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


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response):
    user = db.one(
        """SELECT user_login_id, user_name, user_role, user_password
           FROM tb_user WHERE user_login_id=%s AND deleted_at IS NULL""",
        (payload.login_id,),
    )
    try:
        valid = user and bcrypt.checkpw(payload.password.encode(), user["user_password"].encode())
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    response.set_cookie(
        "session", serializer().dumps(user["user_login_id"]), max_age=SESSION_MAX_AGE,
        httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/",
    )
    return {key: user[key] for key in ("user_login_id", "user_name", "user_role")}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("session", path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")


@app.get("/api/auth/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return user


@app.get("/api/recommendations/{market}")
def recommendations(market: Literal["stock", "upbit"], user: Annotated[dict, Depends(current_user)]):
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
    if market == "upbit":
        key = db.one("SELECT access_key,secret_key FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
        owned = {}
        ownership_available = True
        if key:
            try:
                accounts = engine.private_upbit("GET", "/v1/accounts", key["access_key"], key["secret_key"])
                owned = {row["currency"]: float(row["balance"]) + float(row["locked"]) for row in accounts}
            except (httpx.HTTPError, ValueError) as error:
                ownership_available = False
                engine.record_error("UPBIT", "RECOMMENDATION_BALANCE", error)
        for row in rows:
            currency = row["code"].removeprefix("KRW-")
            row["owned"] = owned.get(currency, 0) > 0 if ownership_available else None
            row["owned_quantity"] = owned.get(currency, 0) if ownership_available else None
    return rows


@app.get("/api/dividends")
def dividends(_: Annotated[dict, Depends(current_user)]):
    return db.all("""SELECT code,name,dividend_rate,ex_div_date,pay_date FROM dividend_stock
        WHERE deleted_at IS NULL ORDER BY dividend_rate DESC""")


@app.get("/api/orders")
def order_history(user: Annotated[dict, Depends(current_user)]):
    key = db.one("SELECT access_key,secret_key FROM tb_upbit_key WHERE user_login_id=%s", (user["user_login_id"],))
    if key:
        try:
            engine.sync_orders(user["user_login_id"], key["access_key"], key["secret_key"])
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
    name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=25)
    password: str | None = Field(None, min_length=8, max_length=200)


class UpbitKeyUpdate(BaseModel):
    access_key: str = Field(min_length=1, max_length=255)
    secret_key: str = Field(min_length=1, max_length=255)


class MailTarget(BaseModel):
    email: str = Field(min_length=3, max_length=255)


@app.post("/api/auth/join", status_code=201)
def join(payload: JoinRequest):
    if db.one("SELECT id FROM tb_user WHERE user_login_id=%s", (payload.login_id,)):
        raise HTTPException(409, "이미 사용 중인 아이디입니다.")
    password = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    now = engine.now()
    db.execute("""INSERT INTO tb_user(id,user_login_id,user_password,user_name,user_role,user_email,user_phone,
        created_at,updated_at,deleted_at) VALUES(nextval('tb_user_seq'),%s,%s,%s,'USER',%s,%s,%s,NULL,NULL)""",
        (payload.login_id, password, payload.name, payload.email, payload.phone, now))
    return {"ok": True}


@app.put("/api/profile")
def update_profile(payload: ProfileUpdate, user: Annotated[dict, Depends(current_user)]):
    encoded = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode() if payload.password else None
    phone = payload.phone if "phone" in payload.model_fields_set else user.get("user_phone")
    db.execute("""UPDATE tb_user SET user_name=%s,user_email=%s,user_phone=%s,
        user_password=COALESCE(%s,user_password),updated_at=%s WHERE id=%s""",
        (payload.name,payload.email,phone,encoded,engine.now(),user["id"]))
    return {"ok": True}


@app.put("/api/upbit/key")
def save_upbit_key(payload: UpbitKeyUpdate, user: Annotated[dict, Depends(current_user)]):
    existing=db.one("SELECT id FROM tb_upbit_key WHERE user_login_id=%s",(user["user_login_id"],))
    if existing:
        db.execute("UPDATE tb_upbit_key SET access_key=%s,secret_key=%s WHERE id=%s",
                   (payload.access_key,payload.secret_key,existing["id"]))
    else:
        db.execute("INSERT INTO tb_upbit_key(id,user_login_id,access_key,secret_key,auto_on) VALUES(nextval('tb_upbit_key_seq'),%s,%s,%s,false)",
                   (user["user_login_id"],payload.access_key,payload.secret_key))
    return {"ok": True}


@app.get("/api/upbit/accounts")
def upbit_accounts(user: Annotated[dict, Depends(current_user)]):
    key=db.one("SELECT * FROM tb_upbit_key WHERE user_login_id=%s",(user["user_login_id"],))
    if not key: return {"total_valuation": 0, "valuation_complete": True, "unpriced_currencies": [], "assets": []}
    try:
        return engine.account_snapshot(key["access_key"],key["secret_key"])
    except httpx.HTTPError as error:
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        engine.record_error("UPBIT", "GET_ACCOUNT" if status is None else f"GET_ACCOUNT_HTTP_{status}", error)
        if status in (401,403) and error.request.url.path == "/v1/accounts":
            db.execute("UPDATE tb_upbit_key SET auto_on=false WHERE id=%s AND access_key=%s AND secret_key=%s",
                       (key["id"], key["access_key"], key["secret_key"]))
        raise HTTPException(502,"Upbit 계좌 조회에 실패했습니다.")


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
def run_job(job: Literal["collect-stock","update-stock","collect-upbit","update-upbit","collect-dividends","auto-order","stock-history","upbit-history"],
            _: Annotated[dict, Depends(master_user)]):
    function={"collect-stock":engine.collect_stock,"update-stock":engine.update_stock,
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
        f"SELECT id, source, operation, error_type, message, created_at FROM trade_error_log{where} ORDER BY id DESC LIMIT 50 OFFSET %s",
        (*values, page * 50),
    )
    return {"items": rows, "page": page, "total": total}


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


@app.get("/api/{path:path}", include_in_schema=False)
@app.get("/api", include_in_schema=False)
def missing_api(path: str = ""):
    raise HTTPException(404, "API 경로를 찾을 수 없습니다.")


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_relative_to(STATIC_DIR) and candidate.is_file():
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
        if Path(path).suffix:
            raise HTTPException(404, "파일을 찾을 수 없습니다.")
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
