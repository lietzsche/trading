import hashlib
import html
import logging
import smtplib
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from urllib.parse import urlencode

import httpx
import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


class TradingEngine:
    """Owns collection, recommendation updates and Upbit order execution."""

    def __init__(self, db, calculation_url: str, enabled: bool):
        self.db, self.calculation_url, self.enabled = db, calculation_url.rstrip("/"), enabled
        self.scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    def start(self):
        if not self.enabled:
            log.warning("Trading scheduler is disabled")
            return
        jobs = [
            (self.collect_upbit, "interval", {"minutes": 15}),
            (self.update_upbit, "interval", {"minutes": 1}),
            (self.auto_order, "interval", {"seconds": 30}),
            (self.collect_stock, "cron", {"day_of_week": "mon-fri", "hour": "8-16", "minute": "*/15"}),
            (self.update_stock, "cron", {"day_of_week": "mon-fri", "hour": "8-15", "minute": "*"}),
            (self.save_stock_history, "cron", {"day_of_week": "mon-fri", "hour": 17, "minute": 30}),
            (self.save_upbit_history, "cron", {"hour": 17, "minute": 30}),
            (self.send_hourly_summary, "cron", {"minute": 0}),
        ]
        for index, (function, trigger, options) in enumerate(jobs):
            self.scheduler.add_job(function, trigger, id=f"trading-{index}", max_instances=1,
                                   coalesce=True, misfire_grace_time=30, **options)
        self.scheduler.start()
        log.info("Python trading scheduler started with %d jobs", len(jobs))

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run(self, source, operation, function):
        try:
            return function()
        except Exception as error:
            log.exception("%s %s failed", source, operation)
            self.record_error(source, operation, error)
            return None

    def record_error(self, source, operation, error):
        message = str(error)[:2000] or type(error).__name__
        for secret in ("access_key", "secret_key", "password", "token"):
            if secret in message.lower():
                message = "Sensitive error details were redacted"
                break
        self.db.execute(
            "INSERT INTO trade_error_log(source,operation,error_type,message,created_at) VALUES(%s,%s,%s,%s,%s)",
            (source[:20], operation[:100], type(error).__name__[:255], message, self.now()),
        )

    @staticmethod
    def now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    def setting(self, name):
        return self.db.one("SELECT * FROM deal_settings WHERE name=%s AND deleted_at IS NULL", (name,)) or {
            "expected_high_percentage": 10, "expected_low_percentage": -5,
            "highest_price_reference_days": 180, "is_volume_check": False,
        }

    def calc(self, endpoint, payload):
        response = httpx.post(f"{self.calculation_url}{endpoint}", json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def upbit_public(path, params=None):
        response = httpx.get(f"https://api.upbit.com{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def upbit_prices(self, market, count):
        rows = self.upbit_public("/v1/candles/days", {"market": market, "count": min(count, 200)})
        return [{"close": r["trade_price"], "open": r["opening_price"], "high": r["high_price"],
                 "low": r["low_price"], "diff": r.get("change_price", 0),
                 "volume": r["candle_acc_trade_volume"]} for r in rows]

    def collect_upbit(self):
        return self.run("UPBIT", "SCHEDULE_SAVE", self._collect_upbit)

    def _collect_upbit(self):
        setting = self.setting("upbit")
        markets = self.upbit_public("/v1/market/all", {"isDetails": "false"})
        instruments = []
        for market in markets:
            code = market["market"]
            if not code.startswith("KRW-"):
                continue
            label = self.db.one("SELECT id FROM upbit_history_label WHERE code=%s AND deleted_at IS NULL", (code,))
            if not label:
                self.db.execute("""INSERT INTO upbit_history_label(id,code,name,created_at,updated_at,deleted_at)
                    VALUES(nextval('upbit_history_label_seq'),%s,%s,%s,NULL,NULL)""",
                    (code, market["korean_name"], self.now()))
            try:
                prices = self.upbit_prices(code, setting["highest_price_reference_days"])
                instruments.append({"code": code, "name": market["korean_name"], "prices": prices})
            except Exception as error:
                self.record_error("UPBIT", "FETCH_PRICE", error)
        selected = self.calc("/v1/recommendations/select", {
            "instruments": instruments, "low_percentage": setting["expected_low_percentage"],
            "high_percentage": setting["expected_high_percentage"],
            "volume_check": setting["is_volume_check"], "amplitude_check": False,
        })["selected_codes"]
        by_code = {item["code"]: item for item in instruments}
        for code in selected:
            if self.db.one("SELECT id FROM upbit WHERE code=%s AND deleted_at IS NULL", (code,)):
                continue
            item, close = by_code[code], by_code[code]["prices"][0]["close"]
            low = close * (1 + setting["expected_low_percentage"] / 100)
            high = close * (1 + setting["expected_high_percentage"] / 100)
            self.db.execute("""INSERT INTO upbit(id,code,name,origin_minimum_selling_price,
                origin_expected_selling_price,minimum_selling_price,expected_selling_price,temp_price,
                setting_price,pricing_reference_date,renewal_cnt,created_at,deleted_at,updated_at)
                VALUES(nextval('upbit_seq'),%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,NULL,NULL)""",
                (code, item["name"], low, high, low, high, close, close, self.now(), self.now()))

    def update_upbit(self):
        return self.run("UPBIT", "SCHEDULE_UPDATE", lambda: self._update_positions("upbit", self.upbit_prices))

    @staticmethod
    def stock_prices(code, count):
        pages = max(1, min(20, (count + 9) // 10)); prices = []
        for page in range(1, pages + 1):
            response = httpx.get("https://finance.naver.com/item/sise_day.nhn",
                                 params={"code": code, "page": page},
                                 headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            response.raise_for_status(); soup = BeautifulSoup(response.text, "html.parser")
            for row in soup.select("table.type2 tr"):
                cells = [cell.get_text(strip=True).replace(",", "") for cell in row.select("td")]
                if len(cells) < 7 or not cells[0]: continue
                prices.append({"close": float(cells[1]), "diff": 0, "open": float(cells[3]),
                               "high": float(cells[4]), "low": float(cells[5]), "volume": float(cells[6])})
        return prices[:count]

    def collect_stock(self):
        return self.run("STOCK", "SCHEDULE_SAVE", self._collect_stock)

    def _collect_stock(self):
        setting = self.setting("stock")
        labels = self.db.all("SELECT DISTINCT code,name FROM stock_history_label WHERE deleted_at IS NULL")
        instruments = []
        for label in labels:
            try:
                instruments.append({"code": label["code"], "name": label["name"],
                                    "prices": self.stock_prices(label["code"], setting["highest_price_reference_days"])})
            except Exception as error: self.record_error("STOCK", "FETCH_PRICE", error)
        selected = self.calc("/v1/recommendations/select", {
            "instruments": instruments, "low_percentage": setting["expected_low_percentage"],
            "high_percentage": setting["expected_high_percentage"],
            "volume_check": setting["is_volume_check"], "amplitude_check": True,
        })["selected_codes"]
        by_code = {item["code"]: item for item in instruments}
        for code in selected:
            if self.db.one("SELECT id FROM stock WHERE code=%s AND deleted_at IS NULL", (code,)): continue
            item, close = by_code[code], by_code[code]["prices"][0]["close"]
            low = close * (1 + setting["expected_low_percentage"] / 100); high = close * (1 + setting["expected_high_percentage"] / 100)
            self.db.execute("""INSERT INTO stock(id,code,name,origin_minimum_selling_price,
              origin_expected_selling_price,minimum_selling_price,expected_selling_price,temp_price,
              setting_price,pricing_reference_date,renewal_cnt,created_at,deleted_at,updated_at)
              VALUES(nextval('stock_seq'),%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,NULL,NULL)""",
              (code,item["name"],low,high,low,high,close,close,self.now(),self.now()))

    def update_stock(self):
        return self.run("STOCK", "SCHEDULE_UPDATE", lambda: self._update_positions("stock", self.stock_prices))

    def save_stock_history(self):
        return self.run("STOCK", "SCHEDULE_SAVE_HISTORY",
                        lambda: self._save_history("stock", "stock_history_label", self.stock_prices))

    def save_upbit_history(self):
        return self.run("UPBIT", "SCHEDULE_SAVE_HISTORY",
                        lambda: self._save_history("upbit", "upbit_history_label", self.upbit_prices))

    def _save_history(self, source, label_table, loader):
        target=f"{source}_history"; today=datetime.now().strftime("%Y-%m-%d")
        for label in self.db.all(f"SELECT code,name FROM {label_table} WHERE deleted_at IS NULL"):
            if self.db.one(f"SELECT id FROM {target} WHERE code=%s AND created_at LIKE %s LIMIT 1",(label["code"],f"{today}%")):
                continue
            try:
                prices=loader(label["code"],1)
                if not prices: continue
                price=prices[0]
                self.db.execute(f"""INSERT INTO {target}(id,code,name,close,diff,open,high,low,volume,
                    created_at,updated_at,deleted_at) VALUES(nextval('{target}_seq'),%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)""",
                    (label["code"],label["name"],price["close"],price.get("diff",0),price.get("open",0),
                     price["high"],price["low"],price["volume"],self.now()))
            except Exception as error:
                self.record_error(source.upper(),"SAVE_HISTORY_ITEM",error)

    def _update_positions(self, table, price_loader):
        setting = self.setting(table); positions = self.db.all(f"SELECT * FROM {table} WHERE deleted_at IS NULL")
        if not positions: return
        payload = []
        for item in positions:
            payload.append({"code":item["code"],"name":item["name"],"prices":price_loader(item["code"],1),
                "expected_selling_price":item["expected_selling_price"],"minimum_selling_price":item["minimum_selling_price"],
                "temp_price":item["temp_price"],"setting_price":item["setting_price"],"renewal_count":item["renewal_cnt"]})
        results = self.calc("/v1/recommendations/update", {"positions":payload,
            "high_multiplier":1+setting["expected_high_percentage"]/100,
            "low_multiplier":1+setting["expected_low_percentage"]/100})["positions"]
        for result in results:
            self.db.execute(f"""UPDATE {table} SET expected_selling_price=%s,minimum_selling_price=%s,
                temp_price=%s,setting_price=%s,renewal_cnt=%s,pricing_reference_date=COALESCE(%s,pricing_reference_date),
                updated_at=%s,deleted_at=CASE WHEN %s='DELETE' THEN %s ELSE deleted_at END
                WHERE code=%s AND deleted_at IS NULL""", (result["expected_selling_price"],result["minimum_selling_price"],
                result["temp_price"],result["setting_price"],result["renewal_count"],result.get("pricing_reference_date"),
                self.now(),result["action"],self.now(),result["code"]))

    @staticmethod
    def token(access, secret, params=None):
        payload = {"access_key": access, "nonce": str(uuid.uuid4())}
        if params:
            query = urlencode(params)
            payload.update({"query_hash": hashlib.sha512(query.encode()).hexdigest(), "query_hash_alg":"SHA512"})
        return jwt.encode(payload, secret, algorithm="HS256")

    def private_upbit(self, method, path, access, secret, params=None):
        headers={"Authorization":f"Bearer {self.token(access,secret,params)}"}
        response=httpx.request(method,f"https://api.upbit.com{path}",params=params if method=="GET" else None,
                               json=params if method!="GET" else None,headers=headers,timeout=15)
        response.raise_for_status(); return response.json()

    def auto_order(self):
        return self.run("UPBIT", "AUTO_ORDER", self._auto_order)

    def _auto_order(self):
        markets=[row["code"] for row in self.db.all("SELECT DISTINCT code FROM upbit WHERE deleted_at IS NULL")]
        for key in self.db.all("SELECT * FROM tb_upbit_key WHERE auto_on=true"):
            try: accounts=self.private_upbit("GET","/v1/accounts",key["access_key"],key["secret_key"])
            except httpx.HTTPStatusError as error:
                if error.response.status_code in (401,403):
                    self.db.execute("UPDATE tb_upbit_key SET auto_on=false WHERE id=%s",(key["id"],))
                raise
            actions=self.calc("/v1/auto-trade/decide",{"recommended_markets":markets,
                "balances":[{"currency":a["currency"]} for a in accounts],"minimum_recommendations":3})["actions"]
            for action in actions:
                market=action["market"]
                chance=self.private_upbit("GET","/v1/orders/chance",key["access_key"],key["secret_key"],{"market":market})
                if action["side"]=="BUY":
                    krw=next((a for a in accounts if a["currency"]=="KRW"),None)
                    if not krw: continue
                    amount=(1-float(chance["bid_fee"]))*float(krw["balance"])
                    if amount <= float(chance["market"]["bid"]["min_total"]): continue
                    params={"market":market,"side":"bid","price":str(amount),"ord_type":"price"}
                else:
                    currency=market.removeprefix("KRW-"); held=next((a for a in accounts if a["currency"]==currency),None)
                    if not held: continue
                    params={"market":market,"side":"ask","volume":chance["ask_account"]["balance"],"ord_type":"market"}
                order=self.private_upbit("POST","/v1/orders",key["access_key"],key["secret_key"],params)
                self.save_order(key["user_login_id"],order)
                accounts=self.private_upbit("GET","/v1/accounts",key["access_key"],key["secret_key"])

    def save_order(self, login_id, order):
        columns=["uuid","side","ord_type","price","state","market","created_at","volume","remaining_volume",
                 "reserved_fee","remaining_fee","paid_fee","locked","executed_volume","trades_count","time_in_force","identifier"]
        values=[order.get(c) for c in columns]
        self.db.execute(f"INSERT INTO upbit_order_history(id,login_id,{','.join(columns)},deleted_at,updated_at) VALUES(nextval('upbit_order_history_seq'),%s,{','.join(['%s']*len(columns))},NULL,NULL)",(login_id,*values))

    def send_hourly_summary(self):
        return self.run("SYSTEM", "SCHEDULE_MAIL", self._send_hourly_summary)

    def _send_hourly_summary(self):
        token=self.db.one("SELECT from_email,gmail_token FROM gmail_token WHERE deleted_at IS NULL ORDER BY id DESC LIMIT 1")
        targets=self.db.all("SELECT email FROM target_mail WHERE deleted_at IS NULL")
        if not token or not targets: return
        rows=self.db.all("SELECT code,name,temp_price,expected_selling_price FROM upbit WHERE deleted_at IS NULL")
        body="<h2>UPbit 선택 종목</h2>"+"".join(f"<p>{html.escape(r['name'])} ({html.escape(r['code'])}): {r['temp_price']} / {r['expected_selling_price']}</p>" for r in rows)
        with smtplib.SMTP("smtp.gmail.com",587,timeout=20) as server:
            server.starttls(); server.login(token["from_email"],token["gmail_token"])
            for target in targets:
                message=MIMEText(body,"html","utf-8"); message["Subject"]="UPbit - 선택 종목"; message["From"]=token["from_email"]; message["To"]=target["email"]
                server.send_message(message)
