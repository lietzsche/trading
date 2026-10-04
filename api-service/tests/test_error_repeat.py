from contextlib import contextmanager
from datetime import datetime,timedelta
import pytest
from app.trading import TradingEngine

class ErrorDatabase:
    def __init__(self):self.rows=[];self.calls=[];self.commits=0;self.now=datetime.now()
    @contextmanager
    def connection(self):
        yield self
        self.commits+=1
    @contextmanager
    def cursor(self):yield self
    def execute(self,sql,params=()):
        self.calls.append((sql,params));self.result=None
        if sql.startswith('SELECT id FROM trade_error_log'):
            found=[row for row in self.rows if row['group']==params and row['last_seen_at']>self.now-timedelta(minutes=10)]
            self.result={'id':found[-1]['id']} if found else None
        elif sql.startswith('UPDATE trade_error_log'):
            row=next(row for row in self.rows if row['id']==params[0]);row['repeat_count']+=1;row['last_seen_at']=self.now
        elif sql.startswith('INSERT INTO trade_error_log'):
            self.rows.append({'id':len(self.rows)+1,'group':params[:3],'message':params[3],'repeat_count':1,'last_seen_at':self.now})
    def fetchone(self):return self.result

def test_error_repeat_100_occurrences_one_row_and_original_message():
    db=ErrorDatabase();engine=TradingEngine(db,'http://calculation',False)
    try:
        for index in range(100):engine.record_error('UPBIT','FETCH_PRICE',ValueError(f'coin {index}'))
        assert len(db.rows)==1 and db.rows[0]['repeat_count']==100
        assert db.rows[0]['message']=='coin 0' and db.commits==100
        assert sum('pg_advisory_xact_lock' in sql for sql,_ in db.calls)==100
        assert any('FOR UPDATE' in sql for sql,_ in db.calls)
    finally:engine.stop()

def test_error_repeat_after_ten_minutes_creates_new_row():
    db=ErrorDatabase();engine=TradingEngine(db,'http://calculation',False)
    try:
        engine.record_error('UPBIT','FETCH_PRICE',ValueError('first'))
        db.now+=timedelta(minutes=10,seconds=1)
        engine.record_error('UPBIT','FETCH_PRICE',ValueError('second'))
        assert [row['repeat_count'] for row in db.rows]==[1,1]
    finally:engine.stop()

def test_error_repeat_sliding_window_and_distinct_groups():
    db=ErrorDatabase();engine=TradingEngine(db,'http://calculation',False)
    try:
        engine.record_error('UPBIT','FETCH_PRICE',ValueError('first'))
        for _ in range(4):
            db.now+=timedelta(minutes=9);engine.record_error('UPBIT','FETCH_PRICE',ValueError('again'))
        engine.record_error('STOCK','FETCH_PRICE',ValueError('other'))
        engine.record_error('UPBIT','SAVE_HISTORY_ITEM',ValueError('other'))
        engine.record_error('UPBIT','FETCH_PRICE',RuntimeError('other'))
        assert len(db.rows)==4 and db.rows[0]['repeat_count']==5
    finally:engine.stop()

def test_error_repeat_redacts_sensitive_initial_message():
    db=ErrorDatabase();engine=TradingEngine(db,'http://calculation',False)
    try:
        engine.record_error('UPBIT','FETCH_PRICE',ValueError('access_key=secret'))
        assert db.rows[0]['message']=='Sensitive error details were redacted'
    finally:engine.stop()
