"""Bounded, cached US watchlist data. Not a broker or an execution adapter."""
import math
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

DEFAULT_SYMBOLS='AAPL,MSFT,NVDA,AMZN,GOOGL,META,BRK-B,JPM,V,MA,UNH,JNJ,PG,KO,PEP,ABBV,MRK,XOM,CVX,O,MO,PM,VZ,T,IBM,CSCO,TXN,ADP,MCD,WMT,COST,HD,LOW,CAT,NEE,DUK,SO,SCHD,VYM,DGRO'
US_PATTERN=r'US:[A-Z][A-Z0-9-]{0,14}'

def is_us_symbol(code):
    return bool(re.fullmatch(US_PATTERN,code or ''))

def us_universe():
    symbols=list(dict.fromkeys(value.strip().upper() for value in os.getenv('US_STOCK_SYMBOLS',DEFAULT_SYMBOLS).split(',') if value.strip()))
    if len(symbols)>100 or any(not is_us_symbol('US:'+symbol) for symbol in symbols):
        raise ValueError('US_STOCK_SYMBOLS는 유효한 미국 티커 최대 100개여야 합니다.')
    return [{'code':'US:'+symbol,'name':symbol} for symbol in symbols]

def chart_result(payload):
    chart=payload.get('chart') or {}
    rows=chart.get('result') or []
    if chart.get('error') or not rows:
        raise ValueError('미국 종목 시세를 찾지 못했습니다.')
    result=rows[0]
    if result.get('meta',{}).get('currency')!='USD':
        raise ValueError('USD로 거래되는 미국 종목만 지원합니다.')
    return result

def chart_bars(payload, completed_only=False):
    result=chart_result(payload)
    quotes=result.get('indicators',{}).get('quote') or [{}]
    quote=quotes[0]; bars=[]
    today=datetime.now(ZoneInfo('America/New_York')).date()
    for index,stamp in enumerate(result.get('timestamp') or []):
        try:
            day=datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date()
            if completed_only and day>=today: continue
            bar={key:float(quote[key][index]) for key in ('open','high','low','close','volume')}
            if not all(math.isfinite(v) for v in bar.values()) or min(bar[k] for k in ('open','high','low','close'))<=0 or bar['volume']<0:continue
            if bar['high']<max(bar['open'],bar['close']) or bar['low']>min(bar['open'],bar['close']):continue
            bars.append({'date':day.isoformat(),**bar})
        except (TypeError,ValueError,KeyError,IndexError,OverflowError):continue
    bars=sorted({bar['date']:bar for bar in bars}.values(),key=lambda bar:bar['date'])
    for index,bar in enumerate(bars):bar['diff']=bar['close']-bars[index-1]['close'] if index else 0
    if not bars:raise ValueError('사용 가능한 미국 일봉이 없습니다.')
    return bars

def trailing_dividend(payload, now=None):
    result=chart_result(payload); bars=chart_bars(payload)
    now=now or datetime.now(timezone.utc)
    cutoff=(now-timedelta(days=365)).timestamp()
    # Corporate-action ambiguity must not become a misleading yield.
    if any(float(split.get('date',0))>cutoff for split in (result.get('events',{}).get('splits') or {}).values()):return None
    events=[]
    for event in (result.get('events',{}).get('dividends') or {}).values():
        try:
            amount=float(event['amount']);stamp=float(event['date'])
            if cutoff<stamp<=now.timestamp() and math.isfinite(amount) and amount>0:events.append((stamp,amount))
        except (ValueError,KeyError,TypeError):continue
    if not events:return None
    return {'dividend_rate':sum(amount for _,amount in events)/bars[-1]['close']*100,
            'ex_div_date':datetime.fromtimestamp(max(stamp for stamp,_ in events),ZoneInfo('America/New_York')).date().isoformat(),
            'pay_date':None}

class USRateLimited(RuntimeError):pass

class USMarketData:
    def __init__(self):
        self.cache={};self.lock=threading.Lock();self.last_request=0.;self.cooldown_until=0.

    def chart(self,code):
        if not is_us_symbol(code):raise ValueError('미국 종목은 US:AAPL 형식이어야 합니다.')
        with self.lock:
            now=time.monotonic();cached=self.cache.get(code)
            if cached and cached[0]>now:return cached[1]
            if now<self.cooldown_until:raise USRateLimited('미국 시세 제공자 요청 제한으로 10분간 조회를 쉬고 있습니다.')
            delay=.5-(now-self.last_request)
            if delay>0:time.sleep(delay)
            response=httpx.get('https://query1.finance.yahoo.com/v8/finance/chart/'+code[3:],
                params={'range':'1y','interval':'1d','events':'div,splits'},headers={'User-Agent':'Mozilla/5.0'},timeout=15)
            self.last_request=time.monotonic()
            if response.status_code==429:
                self.cooldown_until=self.last_request+600
                raise USRateLimited('미국 시세 제공자 요청 제한으로 10분간 조회를 쉬고 있습니다.')
            response.raise_for_status()
            if len(response.content)>2_000_000:raise ValueError('미국 시세 응답이 너무 큽니다.')
            payload=response.json();chart_result(payload)
            if len(self.cache)>=100:self.cache.pop(next(iter(self.cache)))
            self.cache[code]=(time.monotonic()+300,payload)
            return payload

    def prices(self,code,count):return list(reversed(chart_bars(self.chart(code))))[:min(count,200)]

us_data=USMarketData()
