import httpx
import pytest
from datetime import datetime,timedelta,timezone
from app.trading import TradingEngine

class Database:
    def __init__(self):self.writes=[];self.unresolved=None
    def execute(self,sql,params):self.writes.append((sql,params))
    def one(self,*args):return self.unresolved
    def all(self,*args):return [self.unresolved] if self.unresolved else []

@pytest.mark.parametrize('recovered',[True,False])
def test_auto_order_response_loss_recovers_or_stops_without_reposting(monkeypatch,recovered):
    db=Database();engine=TradingEngine(db,'http://calculation',False)
    key={'id':1,'user_login_id':'owner','access_key':'a','secret_key':'s'}
    params={'market':'KRW-BTC','side':'bid','identifier':'auto-1-KRW-BTC-BUY-fixed'}
    calls=[];errors=[]
    def private(method,path,*args):
        calls.append((method,path,args[-1]))
        assert db.writes[0][0].startswith('INSERT INTO auto_order_requests')
        if method=='POST':raise httpx.ReadTimeout('response lost')
        if not recovered:raise httpx.ConnectError('unavailable')
        return {'uuid':'accepted','identifier':params['identifier']}
    monkeypatch.setattr(engine,'private_upbit',private)
    monkeypatch.setattr(engine,'record_error',lambda *args: errors.append(args))
    try:
        if recovered:
            assert engine._submit_auto_order(key,params)['uuid']=='accepted'
            assert 'ACCEPTED' in db.writes[-1][0]
        else:
            with pytest.raises(RuntimeError):engine._submit_auto_order(key,params)
            assert 'UNKNOWN' in db.writes[-1][0] and len(errors)==1
        assert [(method,path) for method,path,_ in calls]==[('POST','/v1/orders'),('GET','/v1/order')]
        assert calls[1][2]=={'identifier':params['identifier']}
    finally:engine.stop()

def test_unresolved_order_blocks_next_cycle_after_failed_get_without_post(monkeypatch):
    db=Database();db.unresolved={'identifier':'unknown','market':'KRW-BTC','created_at':datetime.now(timezone.utc)}
    engine=TradingEngine(db,'http://calculation',False)
    calls=[]
    def unavailable(method,*args):
        assert method=='GET';calls.append(method);raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(engine,'private_upbit',unavailable)
    try:
        with pytest.raises(RuntimeError):engine._auto_order_for_key({'id':1,'access_key':'a','secret_key':'s'},[])
        assert db.writes==[] and calls==['GET']
    finally:engine.stop()


@pytest.mark.parametrize('status,age,name,expected',[
    (404,180,'order_not_found','rejected'),(400,180,'order_not_found','rejected'),
    (404,30,'order_not_found','blocked'),(500,180,'order_not_found','blocked'),
    (401,180,'order_not_found','blocked'),(403,180,'out_of_scope','blocked'),
    (400,180,'validation_error','blocked'),(0,180,'network','blocked')])
def test_reconcile_missing_old_only_rejects_and_never_posts(monkeypatch,status,age,name,expected):
    db=Database();db.unresolved={'identifier':'id','market':'KRW-BTC','created_at':datetime.now(timezone.utc)-timedelta(seconds=age)}
    engine=TradingEngine(db,'http://calculation',False);calls=[]
    def lookup(method,path,*args):
        assert method=='GET' and path=='/v1/order';calls.append(args[-1])
        if not status:raise httpx.ConnectError('offline')
        httpx.Response(status,json={'error':{'name':name}},request=httpx.Request('GET','https://api.upbit.com/v1/order')).raise_for_status()
    monkeypatch.setattr(engine,'private_upbit',lookup)
    try:
        result=engine.reconcile_only({'id':1,'access_key':'a','secret_key':'s'})
        assert result[expected]==1 and calls==[{'identifier':'id'}]
        if expected=='blocked':assert db.writes==[]
        else:assert len(db.writes)==1 and "status='REJECTED'" in db.writes[0][0]
        assert not engine._auto_order_lock.locked()
    finally:engine.stop()


@pytest.mark.parametrize('history_exists',[False,True])
def test_reconcile_confirmed_saves_history_once_and_accepts_without_post(monkeypatch,history_exists):
    db=Database();db.unresolved={'identifier':'id','market':'KRW-BTC','created_at':datetime.now(timezone.utc)}
    engine=TradingEngine(db,'http://calculation',False);saved=[];calls=[]
    monkeypatch.setattr(db,'one',lambda *args: {'id':1} if history_exists else None)
    def lookup(method,path,*args):
        assert method=='GET';calls.append(path)
        return {'uuid':'uuid','identifier':'id','market':'KRW-BTC'}
    monkeypatch.setattr(engine,'private_upbit',lookup)
    monkeypatch.setattr(engine,'save_order',lambda *args: saved.append(args))
    try:
        assert engine.reconcile_only({'id':1,'user_login_id':'owner','access_key':'a','secret_key':'s'})=={'accepted':1,'rejected':0,'blocked':0}
        assert len(saved)==int(not history_exists) and calls==['/v1/order']
        assert "status='ACCEPTED'" in db.writes[0][0]
    finally:engine.stop()


def test_reconcile_mismatched_response_keeps_blocked(monkeypatch):
    db=Database();db.unresolved={'identifier':'id','market':'KRW-BTC'}
    engine=TradingEngine(db,'http://calculation',False)
    monkeypatch.setattr(engine,'private_upbit',lambda *args: {'uuid':'uuid','identifier':'other','market':'KRW-BTC'})
    try:
        assert engine.reconcile_only({'id':1,'access_key':'a','secret_key':'s'})['blocked']==1
        assert db.writes==[]
    finally:engine.stop()
