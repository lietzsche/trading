import hashlib
import html
import json
import logging
import os
import re
import smtplib
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from urllib.parse import unquote, urlencode

import httpx
import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from app.us_market import us_data, us_universe, is_us_symbol, chart_result, trailing_dividend, USRateLimited

log = logging.getLogger(__name__)


class TradingEngine:
    """Owns collection, recommendation updates and Upbit order execution."""

    def __init__(self, db, calculation_url: str, enabled: bool):
        self.db, self.calculation_url, self.enabled = db, calculation_url.rstrip("/"), enabled
        self.scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._auto_order_lock = threading.Lock()
        self._upbit_lock = threading.Lock()
        self._last_upbit_request = 0.0
        self.error_retention_days=max(1,min(3650,int(os.getenv('ERROR_LOG_RETENTION_DAYS','30'))))
        self.error_max_records=max(100,min(1000000,int(os.getenv('ERROR_LOG_MAX_RECORDS','10000'))))
        self._upbit_client = httpx.Client(timeout=15, headers={"User-Agent": "Trading/2.0"})

    def start(self):
        if not self.enabled:
            log.warning("Trading scheduler is disabled")
            return
        jobs = [
            (self.collect_upbit, "interval", {"minutes": 15}),
            (self.update_upbit, "interval", {"minutes": 1}),
            (self.auto_order, "interval", {"seconds": 30}),
            (self.collect_stock, "cron", {"day_of_week": "mon-fri", "hour": 8, "minute": 10}),
            (self.update_stock, "cron", {"day_of_week": "mon-fri", "hour": "8-15", "minute": "*"}),
            (self.collect_us_stock,"cron",{"day_of_week":"mon-fri","hour":8,"minute":30,"timezone":"America/New_York"}),
            (self.update_us_stock,"cron",{"day_of_week":"mon-fri","hour":"9-16","minute":"*/5","timezone":"America/New_York"}),
            (self.save_us_stock_history,"cron",{"day_of_week":"mon-fri","hour":17,"minute":30,"timezone":"America/New_York"}),
            (self.collect_us_dividends,"cron",{"hour":18,"minute":0,"timezone":"America/New_York"}),
            (self.prune_errors,"interval",{"hours":1}),
            (self.save_stock_history, "cron", {"day_of_week": "mon-fri", "hour": 17, "minute": 30}),
            (self.save_upbit_history, "cron", {"hour": 17, "minute": 30}),
            (self.collect_dividends, "cron", {"hour": 17, "minute": 30}),
            (self.send_hourly_summary, "cron", {"minute": 0}),
        ]
        for index, (function, trigger, options) in enumerate(jobs):
            self.scheduler.add_job(function, trigger, id=f"trading-{index}", max_instances=1,
                                   coalesce=True, misfire_grace_time=30, **options)
        self.scheduler.start()
        if not self.db.one("SELECT id FROM dividend_stock WHERE deleted_at IS NULL LIMIT 1"):
            self.scheduler.add_job(self.collect_dividends, "date", id="seed-dividends")
        if not self.db.one("SELECT id FROM stock_history_label WHERE code LIKE %s AND deleted_at IS NULL LIMIT 1",('US:%',)):
            self.scheduler.add_job(self.collect_us_stock,'date',id='seed-us-stock')
            self.scheduler.add_job(self.collect_us_dividends,'date',id='seed-us-dividends')
        self.scheduler.add_job(self.prune_errors,'date',id='initial-error-retention')
        log.info("Python trading scheduler started with %d jobs", len(jobs))

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._upbit_client.close()

    def run(self, source, operation, function):
        try:
            return function()
        except Exception as error:
            log.exception("%s %s failed", source, operation)
            self.record_error(source, operation, error)
            return {"status": "ERROR"}

    def record_error(self, source, operation, error):
        message = str(error)[:2000] or type(error).__name__
        for secret in ("access_key", "secret_key", "password", "token"):
            if secret in message.lower():
                message = "Sensitive error details were redacted"
                break
        group=(source[:20],operation[:100],type(error).__name__[:255])
        # A transaction-level advisory lock also protects the no-row/first-insert case.
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                           (json.dumps(group,ensure_ascii=False),))
            cursor.execute("""SELECT id FROM trade_error_log WHERE source=%s AND operation=%s AND error_type=%s
                AND COALESCE(last_seen_at,created_at)::timestamp > clock_timestamp()-interval '10 minutes'
                ORDER BY COALESCE(last_seen_at,created_at) DESC,id DESC LIMIT 1 FOR UPDATE""",group)
            previous=cursor.fetchone()
            if previous:
                cursor.execute("""UPDATE trade_error_log SET repeat_count=repeat_count+1,
                    last_seen_at=to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US') WHERE id=%s""",(previous['id'],))
            else:
                cursor.execute("""INSERT INTO trade_error_log(source,operation,error_type,message,created_at,last_seen_at)
                    VALUES(%s,%s,%s,%s,to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US'),
                    to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US'))""",(*group,message))

    @staticmethod
    def now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    def error_retention_policy(self):
        return {'days':self.error_retention_days,'max_records':self.error_max_records}

    def prune_errors(self):
        cutoff=(datetime.now()-timedelta(days=self.error_retention_days)).strftime('%Y-%m-%d %H:%M:%S.%f')
        # Both deletions are in one transaction. Keep newest IDs; other tables are untouched.
        with self.db.connection() as connection,connection.cursor() as cursor:
            cursor.execute('DELETE FROM trade_error_log WHERE COALESCE(last_seen_at,created_at) < %s',(cutoff,))
            expired=cursor.rowcount
            cursor.execute('''DELETE FROM trade_error_log WHERE id IN
                (SELECT id FROM trade_error_log ORDER BY COALESCE(last_seen_at,created_at) DESC,id DESC OFFSET %s)''',(self.error_max_records,))
            excess=cursor.rowcount
        log.info('Error retention removed %d expired and %d excess records',expired,excess)
        return {'expired':expired,'excess':excess,**self.error_retention_policy()}

    def setting(self, name):
        return self.db.one("SELECT * FROM deal_settings WHERE name=%s AND deleted_at IS NULL", (name,)) or {
            "expected_high_percentage": 10, "expected_low_percentage": -5,
            "highest_price_reference_days": 180, "is_volume_check": False,
        }

    def calc(self, endpoint, payload):
        response = httpx.post(f"{self.calculation_url}{endpoint}", json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    def upbit_public(self, path, params=None):
        for attempt in range(5):
            with self._upbit_lock:
                delay = 0.13 - (time.monotonic() - self._last_upbit_request)
                if delay > 0:
                    time.sleep(delay)
                try:
                    response = self._upbit_client.get(f"https://api.upbit.com{path}", params=params)
                except httpx.ConnectError:
                    if attempt == 4:
                        raise
                    time.sleep(0.5 * (attempt + 1))
                    continue
                finally:
                    self._last_upbit_request = time.monotonic()
            if response.status_code != 429:
                response.raise_for_status()
                return response.json()
            retry_after = response.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else max(1, attempt + 1))
        response.raise_for_status()

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
        codes = self._validated_upbit_codes(markets)
        now = self.now()
        self.db.execute("""UPDATE upbit SET deleted_at=%s,updated_at=%s
            WHERE deleted_at IS NULL AND NOT (code=ANY(%s))""", (now,now,codes))
        instruments = []
        for market in markets:
            code = market["market"]
            if not code.startswith("KRW-"):
                continue
            label = self.db.one("SELECT id,name,deleted_at FROM upbit_history_label WHERE code=%s ORDER BY id DESC LIMIT 1", (code,))
            if label and (label.get('deleted_at') is not None or label.get('name') != market['korean_name']):
                self.db.execute("""UPDATE upbit_history_label SET deleted_at=NULL,name=%s
                    WHERE id=%s AND (deleted_at IS NOT NULL OR name IS DISTINCT FROM %s)""",
                    (market["korean_name"],label["id"],market['korean_name']))
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
        if is_us_symbol(code):return us_data.prices(code,count)
        prices, cursor = [], None
        while len(prices) < min(count, 200):
            params = {"size": min(100, count - len(prices))}
            if cursor:
                params["cursor"] = cursor
            response = httpx.get(f"https://stock.naver.com/api/stockSecurity/items/v2/domestic/{code}/daily-prices",
                                 params=params, headers={"User-Agent": "Mozilla/5.0",
                                 "Referer": "https://stock.naver.com/"}, timeout=15)
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("items", []) if isinstance(payload, dict) else []
            for row in rows:
                try:
                    prices.append({"close": float(row["closingPrice"]), "diff": float(row.get("changePrice") or 0),
                                   "open": float(row["openingPrice"]), "high": float(row["highPrice"]),
                                   "low": float(row["lowPrice"]), "volume": float(row["tradingVolume"])})
                except (KeyError, TypeError, ValueError):
                    continue
            cursor = payload.get("cursor") if isinstance(payload, dict) and payload.get("hasNext") else None
            if not rows or not cursor:
                break
        return prices[:count]

    def collect_stock(self):
        return self.run("STOCK", "SCHEDULE_SAVE", self._collect_stock)

    def collect_us_stock(self):
        return self.run('STOCK_US','SCHEDULE_SAVE',lambda:self._collect_stock('US'))

    def _collect_stock(self,region='KR'):
        setting = self.setting("stock")
        labels = us_universe() if region=='US' else self.db.all("SELECT DISTINCT code,name FROM stock_history_label WHERE deleted_at IS NULL AND code NOT LIKE %s",('US:%',))
        if region=='US' and not labels:return {'status':'SKIPPED'}
        if region=='US':
            for label in labels:
                if not self.db.one('SELECT id FROM stock_history_label WHERE code=%s AND deleted_at IS NULL',(label['code'],)):
                    self.db.execute('''INSERT INTO stock_history_label(id,code,name,created_at,updated_at,deleted_at)
                        VALUES(nextval('stock_history_label_seq'),%s,%s,%s,NULL,NULL)''',(label['code'],label['name'],self.now()))
        if not labels:
            labels = self.stock_universe()
            self.db.executemany("""INSERT INTO stock_history_label(id,code,name,created_at,updated_at,deleted_at)
                VALUES(nextval('stock_history_label_seq'),%s,%s,%s,NULL,NULL)""",
                [(label["code"], label["name"], self.now()) for label in labels])
        instruments = []
        for label in labels:
            try:
                instruments.append({"code": label["code"], "name": label["name"],
                                    "prices": self.stock_prices(label["code"], setting["highest_price_reference_days"])})
            except Exception as error:
                self.record_error('STOCK_US' if region=='US' else 'STOCK','FETCH_PRICE',error)
                if isinstance(error,USRateLimited):break
        if not instruments:return {'status':'ERROR'}
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

    @staticmethod
    def stock_universe():
        response = httpx.get("http://kind.krx.co.kr/corpgeneral/corpList.do",
            params={"method":"download","searchType":"13"}, headers={"User-Agent":"Mozilla/5.0"},
            timeout=30, follow_redirects=True)
        response.raise_for_status()
        rows = BeautifulSoup(response.content, "html.parser").select("tr")
        if not rows:
            raise RuntimeError("한국거래소 종목 목록이 비어 있습니다.")
        headers = [cell.get_text(strip=True) for cell in rows[0].select("th,td")]
        try:
            name_index, market_index, code_index = headers.index("회사명"), headers.index("시장구분"), headers.index("종목코드")
        except ValueError as error:
            raise RuntimeError("한국거래소 종목 목록 형식이 변경되었습니다.") from error
        result = []
        for row in rows[1:]:
            cells = [cell.get_text(strip=True) for cell in row.select("td")]
            if len(cells) > max(name_index, market_index, code_index) and cells[market_index] in {"코스피","코스닥"}:
                result.append({"name":cells[name_index], "code":cells[code_index].zfill(6)})
        if not result:
            raise RuntimeError("코스피/코스닥 종목을 찾지 못했습니다.")
        return result

    def update_stock(self):
        return self.run("STOCK", "SCHEDULE_UPDATE", lambda: self._update_positions("stock", self.stock_prices,'KR'))

    def update_us_stock(self):
        return self.run('STOCK_US','SCHEDULE_UPDATE',lambda:self._update_positions('stock',self.stock_prices,'US'))

    def collect_us_dividends(self):
        return self.run('STOCK_US','SCHEDULE_SAVE_DIVIDENDS',self._collect_us_dividends)

    def _collect_us_dividends(self):
        saved=0
        for label in us_universe():
            try:
                payload=us_data.chart(label['code']);dividend=trailing_dividend(payload)
                if not dividend:
                    self.db.execute('UPDATE dividend_stock SET deleted_at=%s WHERE code=%s AND deleted_at IS NULL',(self.now(),label['code']))
                    continue
                meta=chart_result(payload)['meta'];name=meta.get('longName') or meta.get('shortName') or label['name']
                existing=self.db.one('SELECT id FROM dividend_stock WHERE code=%s AND deleted_at IS NULL',(label['code'],))
                if existing:self.db.execute('''UPDATE dividend_stock SET name=%s,dividend_rate=%s,ex_div_date=%s,
                    pay_date=NULL,updated_at=%s WHERE id=%s''',(name,dividend['dividend_rate'],dividend['ex_div_date'],self.now(),existing['id']))
                else:self.db.execute('''INSERT INTO dividend_stock(id,code,name,dividend_rate,ex_div_date,pay_date,created_at,updated_at,deleted_at)
                    VALUES(nextval('dividend_stock_seq'),%s,%s,%s,%s,NULL,%s,NULL,NULL)''',(label['code'],name,dividend['dividend_rate'],dividend['ex_div_date'],self.now()))
                saved+=1
            except Exception as error:
                self.record_error('STOCK_US','FETCH_DIVIDEND',error)
                if isinstance(error,USRateLimited):break
        return saved

    @staticmethod
    def parse_dividend_page(body):
        rows = []
        for row in BeautifulSoup(body, "html.parser").select("table.type_1 tr"):
            link, cells = row.select_one("td.frst a[href*='code=']"), row.select("td")
            if not link or len(cells) < 5:
                continue
            code_match = re.search(r"(?:\?|&)code=(\d{6})(?:&|$)", link.get("href", ""))
            rate_text = cells[4].get_text(strip=True).replace(",", "")
            try:
                rate = float(rate_text)
            except ValueError:
                continue
            if code_match and rate > 0:
                rows.append({"code": code_match.group(1), "name": link.get_text(strip=True),
                             "dividend_rate": rate})
        return rows

    def collect_dividends(self):
        return self.run("STOCK", "SCHEDULE_SAVE_DIVIDEND_STOCKS", self._collect_dividends)

    def _collect_dividends(self):
        response = httpx.get("https://stock.naver.com/api/domestic/market/stock/dividend",
                             params={"tradeType": "KRX", "marketType": "ALL", "dividend": "dividendRate",
                                     "startIdx": 0, "pageSize": 100},
                             headers={"User-Agent": "Mozilla/5.0", "Referer": "https://stock.naver.com/"}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = []
        for row in payload if isinstance(payload, list) else []:
            try:
                code, name, rate = str(row["itemcode"]), str(row["itemname"]).strip(), float(row["dividendRate"])
            except (KeyError, TypeError, ValueError):
                continue
            if re.fullmatch(r"\d{6}", code) and name and rate > 0:
                items.append({"code": code, "name": name, "dividend_rate": rate})
        if not items:
            raise RuntimeError("배당주 목록이 비어 있습니다.")
        now = self.now()
        for item in items:
            saved = self.db.one("SELECT id FROM dividend_stock WHERE code=%s AND deleted_at IS NULL",
                                (item["code"],))
            if saved:
                self.db.execute("""UPDATE dividend_stock SET name=%s,dividend_rate=%s,
                    updated_at=%s WHERE id=%s""", (item["name"], item["dividend_rate"], now, saved["id"]))
            else:
                self.db.execute("""INSERT INTO dividend_stock(id,code,name,dividend_rate,ex_div_date,
                    pay_date,created_at,updated_at,deleted_at)
                    VALUES(nextval('dividend_stock_seq'),%s,%s,%s,NULL,NULL,%s,NULL,NULL)""",
                    (item["code"], item["name"], item["dividend_rate"], now))
        return len(items)

    def save_stock_history(self):
        return self.run("STOCK", "SCHEDULE_SAVE_HISTORY",
                        lambda: self._save_history("stock", "stock_history_label", self.stock_prices,'KR'))

    def save_us_stock_history(self):
        return self.run('STOCK_US','SCHEDULE_SAVE_HISTORY',lambda:self._save_history('stock','stock_history_label',self.stock_prices,'US'))

    def save_upbit_history(self):
        return self.run("UPBIT", "SCHEDULE_SAVE_HISTORY",
                        self._save_upbit_history)

    @staticmethod
    def _validated_upbit_codes(markets):
        if (not isinstance(markets, list) or not markets or
                any(not isinstance(row, dict) or not isinstance(row.get("market"), str)
                    or not re.fullmatch(r"[A-Z0-9]+-[A-Z0-9]+", row["market"]) for row in markets)):
            raise RuntimeError("Upbit 거래 지원 목록이 비정상입니다. 수집 대상을 유지합니다.")
        codes = sorted({row["market"] for row in markets if row["market"].startswith("KRW-")})
        if not codes:
            raise RuntimeError("Upbit 원화 거래 지원 목록이 비어 있습니다. 수집 대상을 유지합니다.")
        if any(not isinstance(row.get('korean_name'),str) or not row['korean_name'].strip()
               for row in markets if row['market'].startswith('KRW-')):
            raise RuntimeError("Upbit 종목명 형식이 비정상입니다. 수집 대상을 유지합니다.")
        return codes

    def _save_upbit_history(self):
        # A failed/invalid market response must never deactivate existing targets.
        codes = self._validated_upbit_codes(self.upbit_public("/v1/market/all"))
        with self.db.connection() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE upbit_history_label SET deleted_at=%s,updated_at=%s
                WHERE deleted_at IS NULL AND code LIKE 'KRW-%%' AND NOT (code=ANY(%s))""",
                (self.now(),self.now(),codes))
            cursor.execute("""UPDATE upbit_history_label SET deleted_at=NULL,updated_at=%s
                WHERE deleted_at IS NOT NULL AND code=ANY(%s)""", (self.now(),codes))
        self._save_history("upbit", "upbit_history_label", self.upbit_prices)

    def _save_history(self, source, label_table, loader,region=None):
        target=f"{source}_history"; today=datetime.now().strftime("%Y-%m-%d")
        query=f"SELECT code,name FROM {label_table} WHERE deleted_at IS NULL"
        params=()
        if region:query+=' AND code '+('LIKE' if region=='US' else 'NOT LIKE')+' %s';params=('US:%',)
        for label in self.db.all(query,params):
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
                self.record_error('STOCK_US' if region == 'US' else source.upper(),"SAVE_HISTORY_ITEM",error)
                if isinstance(error, USRateLimited):
                    break

    def _update_positions(self, table, price_loader,region=None):
        setting = self.setting(table)
        query=f"SELECT * FROM {table} WHERE deleted_at IS NULL";params=()
        if region:query+=' AND code '+('LIKE' if region=='US' else 'NOT LIKE')+' %s';params=('US:%',)
        positions = self.db.all(query,params)
        if not positions: return
        payload = []
        for item in positions:
            try:
                prices = price_loader(item["code"], 1)
            except Exception as error:
                self.record_error('STOCK_US' if region == 'US' else table.upper(), "UPDATE_PRICE_ITEM", error)
                if isinstance(error, USRateLimited):
                    break
                continue
            payload.append({"code":item["code"],"name":item["name"],"prices":prices,
                "expected_selling_price":item["expected_selling_price"],"minimum_selling_price":item["minimum_selling_price"],
                "temp_price":item["temp_price"],"setting_price":item["setting_price"],"renewal_count":item["renewal_cnt"]})
        if not payload:
            return
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
            query = unquote(urlencode(params, doseq=True))
            payload.update({"query_hash": hashlib.sha512(query.encode()).hexdigest(), "query_hash_alg":"SHA512"})
        return jwt.encode(payload, secret, algorithm="HS256")

    def private_upbit(self, method, path, access, secret, params=None):
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                headers={"Authorization":f"Bearer {self.token(access,secret,params)}"}
                response=self._upbit_client.request(method,f"https://api.upbit.com{path}",
                    params=params if method=="GET" else None,json=params if method!="GET" else None,headers=headers)
                if response.status_code == 429 and attempt + 1 < attempts:
                    time.sleep(max(1, attempt + 1)); continue
                response.raise_for_status(); return response.json()
            except httpx.ConnectError:
                if attempt + 1 == attempts: raise
                time.sleep(0.5 * (attempt + 1))

    def account_snapshot(self, access, secret):
        accounts = self.private_upbit("GET", "/v1/accounts", access, secret)
        tickers = self.upbit_public("/v1/ticker/all", {"quote_currencies": "KRW"})
        prices = {row["market"].removeprefix("KRW-"): float(row["trade_price"]) for row in tickers}
        assets, total, unpriced = [], 0.0, []
        for account in accounts:
            currency = account["currency"]
            quantity = float(account["balance"]) + float(account["locked"])
            if quantity <= 0:
                continue
            current_price = 1.0 if currency == "KRW" else prices.get(currency)
            if current_price is not None and current_price <= 0:
                current_price = None
            valuation = quantity * current_price if current_price is not None else None
            average = float(account["avg_buy_price"])
            purchase = (quantity * average if account.get("unit_currency") == "KRW" else None)
            if currency == "KRW":
                purchase = valuation
            profit_rate = ((valuation - purchase) * 100 / purchase
                           if valuation is not None and purchase is not None and purchase > 0
                           and currency != "KRW" else None)
            if valuation is None:
                unpriced.append(currency)
            else:
                total += valuation
            assets.append({**account, "quantity": quantity, "current_price": current_price,
                           "valuation": valuation, "purchase_amount": purchase, "profit_rate": profit_rate})
        return {"total_valuation": total, "valuation_complete": not unpriced,
                "unpriced_currencies": sorted(unpriced),
                "assets": sorted(assets, key=lambda row: (row["valuation"] is not None,
                                                         row["valuation"] or 0), reverse=True)}

    def manual_market_sell(self, key, market, expected_available):
        """Sell the entire currently available balance once; never retry POST."""
        if not self._auto_order_lock.acquire(blocking=False):
            raise ValueError("다른 주문을 처리 중입니다. 잠시 후 계좌를 새로고침하고 다시 시도해 주세요.")
        try:
            if not isinstance(market, str) or not re.fullmatch(r"KRW-[A-Z0-9]{1,20}", market):
                raise ValueError("유효한 Upbit 원화 마켓이 아닙니다.")
            chance = self.private_upbit("GET", "/v1/orders/chance", key["access_key"], key["secret_key"], {"market": market})
            try:
                available = Decimal(str(chance["ask_account"]["balance"]))
                expected = Decimal(str(expected_available))
                minimum = Decimal(str(chance["market"]["ask"]["min_total"]))
            except (KeyError, TypeError, InvalidOperation):
                raise ValueError("최신 매도 가능 수량을 확인할 수 없습니다.") from None
            if available <= 0:
                raise ValueError("시장가로 매도할 수 있는 잔고가 없습니다.")
            if available != expected:
                raise ValueError("매도 가능 수량이 화면을 연 뒤 변경되었습니다. 계좌를 새로고침한 후 다시 확인해 주세요.")
            ask_types = chance.get("market", {}).get("ask_types")
            if isinstance(ask_types, list) and "market" not in ask_types:
                raise ValueError("이 마켓은 시장가 매도를 지원하지 않습니다.")
            ticker = self.upbit_public("/v1/ticker", {"markets": market})
            try:
                current_price = Decimal(str(ticker[0]["trade_price"]))
            except (KeyError, IndexError, TypeError, InvalidOperation):
                raise ValueError("최소 주문금액 확인을 위한 현재가를 조회하지 못했습니다.") from None
            if available * current_price < minimum:
                raise ValueError("예상 주문금액이 Upbit 최소 매도금액보다 작습니다.")
            active = self.db.one("""SELECT k.id FROM tb_upbit_key k JOIN tb_user u ON u.user_login_id=k.user_login_id
                WHERE k.id=%s AND u.deleted_at IS NULL AND k.access_key=%s AND k.secret_key=%s""",
                (key["id"], key["access_key"], key["secret_key"]))
            if not active:
                raise ValueError("등록된 Upbit 키가 변경되었습니다. 계좌를 새로고침해 주세요.")
            params = {"market": market, "side": "ask", "volume": format(available, "f"), "ord_type": "market",
                      "identifier": f"manual-sell-{key['id']}-{uuid.uuid4()}"}
            order = self.private_upbit("POST", "/v1/orders", key["access_key"], key["secret_key"], params)
            history_saved = True
            try:
                self.save_order(key["user_login_id"], order)
            except Exception:
                history_saved = False
                log.exception("Upbit accepted manual sell but local order history save failed for key id %s", key["id"])
            return {"ok": True, "uuid": order.get("uuid"), "market": market,
                    "volume": params["volume"], "state": order.get("state"), "history_saved": history_saved}
        finally:
            self._auto_order_lock.release()

    def sync_orders(self, login_id, access, secret):
        uuids = [row["uuid"] for row in self.db.all(
            "SELECT uuid FROM upbit_order_history WHERE login_id=%s AND uuid IS NOT NULL ORDER BY id DESC LIMIT 100",
            (login_id,))]
        if not uuids:
            return
        for start in range(0, len(uuids), 100):
            orders = self.private_upbit("GET", "/v1/orders/uuids", access, secret,
                                        {"uuids[]": uuids[start:start + 100]})
            for order in orders:
                self.db.execute("""UPDATE upbit_order_history SET state=%s,price=%s,volume=%s,
                    remaining_volume=%s,executed_volume=%s,paid_fee=%s,trades_count=%s,updated_at=%s
                    WHERE login_id=%s AND uuid=%s""", (order.get("state"), order.get("price"),
                    order.get("volume"), order.get("remaining_volume"), order.get("executed_volume"),
                    order.get("paid_fee"), order.get("trades_count"), self.now(), login_id, order.get("uuid")))

    def order_fills(self, access, secret, uuid):
        # /v1/orders/uuids (used by sync_orders) never returns per-trade fills;
        # market sell orders store no proceeds locally, so realized P&L needs
        # this per-order detail call instead.
        detail = self.private_upbit("GET", "/v1/order", access, secret, {"uuid": uuid})
        trades = detail.get("trades") if isinstance(detail, dict) else None
        return trades if isinstance(trades, list) else []

    def auto_order(self):
        # APScheduler's max_instances does not cover administrator-triggered runs.
        if not self._auto_order_lock.acquire(blocking=False):
            log.info("Skipping automatic orders: another run is already active")
            return {"status": "SKIPPED", "reason": "already_running"}
        try:
            return self.run("UPBIT", "AUTO_ORDER", self._auto_order)
        finally:
            self._auto_order_lock.release()

    def _auto_order(self):
        # BUY consumes the available KRW on the first actionable market, so this
        # order must exactly match the recommendation screen's priority order.
        markets = [row["code"] for row in self.db.all("""SELECT code FROM upbit
            WHERE deleted_at IS NULL
            ORDER BY renewal_cnt DESC,
                     (expected_selling_price-temp_price)
                       / NULLIF(expected_selling_price-minimum_selling_price,0) ASC NULLS LAST,
                     id DESC""")]
        keys = self.db.all("""SELECT k.* FROM tb_upbit_key k
            JOIN tb_user u ON u.user_login_id=k.user_login_id
            WHERE k.auto_on=true AND u.deleted_at IS NULL""")
        completed, failed = 0, 0
        for key in keys:
            try:
                self._auto_order_for_key(key, markets)
                completed += 1
            except Exception as error:
                # A failed credential/provider request must not starve other users.
                failed += 1
                log.exception("Automatic orders failed for key id %s", key["id"])
                self.record_error("UPBIT", f"AUTO_ORDER_ACCOUNT_{key['id']}", error)
        return {"status": "PARTIAL" if failed else "OK", "completed_accounts": completed,
                "failed_accounts": failed}

    def _auto_order_for_key(self, key, markets):
        try:
            accounts = self.private_upbit("GET", "/v1/accounts", key["access_key"], key["secret_key"])
        except httpx.HTTPStatusError as error:
            if error.response.status_code in (401, 403):
                self.db.execute("""UPDATE tb_upbit_key SET auto_on=false
                    WHERE id=%s AND access_key=%s AND secret_key=%s""",
                    (key["id"], key["access_key"], key["secret_key"]))
            raise
        actions = self.calc("/v1/auto-trade/decide", {
            "recommended_markets": markets, "balances": [{"currency": a["currency"]} for a in accounts],
            "minimum_recommendations": 3,
        })["actions"]
        recent_manual_sells = {row["market"] for row in self.db.all("""SELECT DISTINCT market
            FROM upbit_order_history
            WHERE login_id=%s AND identifier LIKE 'manual-sell-%%'
              AND CASE
                    WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}T'
                    THEN created_at::timestamptz
                  END >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'""",
            (key["user_login_id"],))}
        for action in actions:
            market = action["market"]
            # Keep automatic trading enabled after a manual exit, but avoid
            # immediately buying back the same asset. The next ranked BUY can proceed.
            if action["side"] == "BUY" and market in recent_manual_sells:
                continue
            try:
                chance = self.private_upbit("GET", "/v1/orders/chance", key["access_key"], key["secret_key"],
                                            {"market": market})
            except httpx.HTTPStatusError as error:
                if not self._missing_upbit_market(error):
                    raise
                self.record_error('UPBIT',f'AUTO_ORDER_MARKET_{market}',error)
                continue
            if action["side"] == "BUY":
                krw = next((a for a in accounts if a["currency"] == "KRW"), None)
                if not krw:
                    continue
                amount = (1 - float(chance["bid_fee"])) * float(krw["balance"])
                if amount <= float(chance["market"]["bid"]["min_total"]):
                    continue
                params = {"market": market, "side": "bid", "price": str(amount), "ord_type": "price"}
            else:
                currency = market.removeprefix("KRW-")
                held = next((a for a in accounts if a["currency"] == currency), None)
                if not held or float(chance["ask_account"]["balance"]) <= 0:
                    continue
                params = {"market": market, "side": "ask", "volume": chance["ask_account"]["balance"],
                          "ord_type": "market"}
            # Account deletion, opt-out, or key replacement during this run stops further orders.
            active = self.db.one("""SELECT k.id FROM tb_upbit_key k
                JOIN tb_user u ON u.user_login_id=k.user_login_id
                WHERE k.id=%s AND k.auto_on=true AND u.deleted_at IS NULL
                  AND k.access_key=%s AND k.secret_key=%s""",
                (key["id"], key["access_key"], key["secret_key"]))
            if not active:
                break
            try:
                order = self.private_upbit("POST", "/v1/orders", key["access_key"], key["secret_key"], params)
            except httpx.HTTPStatusError as error:
                if not self._missing_upbit_market(error):
                    raise
                self.record_error('UPBIT',f'AUTO_ORDER_MARKET_{market}',error)
                continue
            self.save_order(key["user_login_id"], order)
            accounts = self.private_upbit("GET", "/v1/accounts", key["access_key"], key["secret_key"])

    @staticmethod
    def _missing_upbit_market(error):
        if error.response.status_code == 404:
            return True
        if error.response.status_code != 400:
            return False
        try:
            detail = error.response.json().get('error', {})
            return detail.get('name') in {'market_not_found','not_found_market','invalid_market'} or (
                detail.get('message') in {'Code not found','market not found','존재하지 않는 마켓입니다.'})
        except (ValueError,AttributeError):
            return False

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
