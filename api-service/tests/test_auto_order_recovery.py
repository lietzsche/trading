import httpx
import pytest
from app.trading import TradingEngine

class Database:
    def __init__(self):self.writes=[];self.unresolved=None
    def execute(self,sql,params):self.writes.append((sql,params))
    def one(self,*args):return self.unresolved

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

def test_unresolved_order_blocks_next_cycle_without_exchange_calls(monkeypatch):
    db=Database();db.unresolved={'identifier':'unknown','status':'UNKNOWN'}
    engine=TradingEngine(db,'http://calculation',False)
    monkeypatch.setattr(engine,'private_upbit',lambda *args: pytest.fail('No new orders or API calls'))
    try:
        with pytest.raises(RuntimeError):engine._auto_order_for_key({'id':1},[])
        assert db.writes==[]
    finally:engine.stop()
