from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.us_market import USMarketData,USRateLimited,chart_bars,trailing_dividend,us_universe
from app.trading import TradingEngine
from app.ai import AnalysisRequest
from app.ai_engine import _MarketData


def payload():
    return {'chart':{'error':None,'result':[{'meta':{'currency':'USD'},
        'timestamp':[1759361400,1759447800],
        'indicators':{'quote':[{'open':[99,99],'high':[102,102],'low':[98,98],'close':[100,100],'volume':[10,20]}]},
        'events':{'dividends':{'a':{'date':1759361400,'amount':1},'b':{'date':1759447800,'amount':2}}}}]}}


def test_us_ohlcv_order_currency_and_invalid_values():
    body=payload();bars=chart_bars(body)
    assert len(bars)==2 and bars[0]['date']<bars[1]['date']
    assert bars[-1]['close']==100 and bars[-1]['diff']==0
    body['chart']['result'][0]['indicators']['quote'][0]['close'][0]=float('nan')
    assert len(chart_bars(body))==1
    body['chart']['result'][0]['meta']['currency']='CAD'
    with pytest.raises(ValueError,match='USD'):chart_bars(body)


def test_us_completed_history_excludes_current_ny_day():
    body=payload();today=datetime.now(ZoneInfo('America/New_York')).replace(hour=10,minute=0,second=0,microsecond=0)
    body['chart']['result'][0]['timestamp']=[int((today-timedelta(days=1)).timestamp()),int(today.timestamp())]
    assert len(chart_bars(body,completed_only=True))==1


def test_us_trailing_yield_and_unknown_payment_date():
    now=datetime(2025,10,4,tzinfo=timezone.utc)
    result=trailing_dividend(payload(),now=now)
    assert result['dividend_rate']==3 and result['pay_date'] is None
    body=payload();body['chart']['result'][0]['events']['splits']={'s':{'date':1759447800,'numerator':2,'denominator':1}}
    assert trailing_dividend(body,now=now) is None
    assert trailing_dividend(payload(),now=datetime(2027,1,1,tzinfo=timezone.utc)) is None


def test_us_provider_cache_and_rate_limit_cooldown(monkeypatch):
    calls=[]
    def fetch(*args,**kwargs):
        calls.append(args)
        return httpx.Response(200,json=payload(),request=httpx.Request('GET',args[0]))
    monkeypatch.setattr('app.us_market.httpx.get',fetch)
    monkeypatch.setattr('app.us_market.time.monotonic',lambda:100.)
    data=USMarketData();data.chart('US:AAPL');data.chart('US:AAPL')
    assert len(calls)==1
    def limited(*args,**kwargs):
        calls.append(args)
        return httpx.Response(429,request=httpx.Request('GET',args[0]))
    monkeypatch.setattr('app.us_market.httpx.get',limited)
    with pytest.raises(USRateLimited):data.chart('US:MSFT')
    with pytest.raises(USRateLimited):data.chart('US:KO')
    assert len(calls)==2


def test_us_universe_is_bounded_and_validated(monkeypatch):
    monkeypatch.setenv('US_STOCK_SYMBOLS','aapl,KO,AAPL,BRK-B')
    assert [row['code'] for row in us_universe()]==['US:AAPL','US:KO','US:BRK-B']
    monkeypatch.setenv('US_STOCK_SYMBOLS','https://example.org')
    with pytest.raises(ValueError):us_universe()


def test_ai_accepts_us_symbols_and_uses_read_only_us_history(monkeypatch):
    assert AnalysisRequest(market='stock',symbols=['aapl','005930'],prompt='비교').symbols==['US:AAPL','005930']
    monkeypatch.setattr('app.ai_engine.us_data.chart',lambda code:payload())
    market=_MarketData(None,'stock',float('inf'))
    result=market.history('US:AAPL',3)
    assert result['currency']=='USD' and '미국' in result['source']


class RetentionDatabase:
    def __init__(self):self.calls=[];self.rowcount=0;self.committed=False
    @contextmanager
    def connection(self):
        yield self
        self.committed=True
    @contextmanager
    def cursor(self):yield self
    def execute(self,query,params):
        self.calls.append((query,params));self.rowcount=7 if len(self.calls)==1 else 3


def test_error_retention_one_transaction_and_latest_count(monkeypatch):
    monkeypatch.setenv('ERROR_LOG_RETENTION_DAYS','14');monkeypatch.setenv('ERROR_LOG_MAX_RECORDS','500')
    db=RetentionDatabase();engine=TradingEngine(db,'http://calculation',False)
    try:
        result=engine.prune_errors()
        assert result=={'expired':7,'excess':3,'days':14,'max_records':500}
        assert db.committed and len(db.calls)==2
        assert all('DELETE FROM trade_error_log' in query for query,_ in db.calls)
        assert 'ORDER BY id DESC OFFSET %s' in db.calls[1][0] and db.calls[1][1]==(500,)
        cutoff=datetime.strptime(db.calls[0][1][0],'%Y-%m-%d %H:%M:%S.%f')
        assert abs((datetime.now()-cutoff).total_seconds()-14*86400)<5
    finally:engine.stop()


def test_us_collection_preserves_us_codes_and_percent_targets(monkeypatch):
    monkeypatch.setenv('US_STOCK_SYMBOLS','AAPL,KO')
    class DB:
        def __init__(self):self.writes=[]
        def one(self,query,params=()):
            if 'deal_settings' in query:return {'expected_high_percentage':10,'expected_low_percentage':-5,'highest_price_reference_days':30,'is_volume_check':False}
            return None
        def execute(self,query,params=()):self.writes.append((query,params))
    db=DB();engine=TradingEngine(db,'http://calculation',False)
    monkeypatch.setattr(engine,'stock_prices',lambda *args:[{'close':100,'open':99,'high':101,'low':98,'volume':1000}])
    monkeypatch.setattr(engine,'calc',lambda endpoint,body:{'selected_codes':[item['code'] for item in body['instruments']]})
    try:
        engine._collect_stock('US')
        inserted=[params for query,params in db.writes if 'INSERT INTO stock(' in query]
        assert [params[0] for params in inserted]==['US:AAPL','US:KO']
        assert all(params[2]==95 and params[3]==pytest.approx(110) for params in inserted)
    finally:engine.stop()


def test_us_scheduler_has_new_york_timezone_and_five_minute_updates():
    class Scheduler:
        def __init__(self):self.running=False;self.jobs=[]
        def add_job(self,function,trigger,**kwargs):self.jobs.append((function.__name__,trigger,kwargs))
        def start(self):self.running=True
        def shutdown(self,**kwargs):self.running=False
    class DB:
        def one(self,*args):return {'id':1}
    engine=TradingEngine(DB(),'http://calculation',True);engine.scheduler=Scheduler()
    try:
        engine.start();jobs={name:options for name,_,options in engine.scheduler.jobs}
        assert jobs['update_us_stock']['timezone']=='America/New_York'
        assert jobs['update_us_stock']['minute']=='*/5'
        assert jobs['collect_us_stock']['timezone']=='America/New_York'
        assert any(name=='prune_errors' and options.get('hours')==1 for name,_,options in engine.scheduler.jobs)
    finally:engine.stop()
