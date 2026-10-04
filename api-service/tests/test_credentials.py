from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from app.credentials import encrypt_upbit,upbit_credentials,migrate_upbit_credentials,PREFIX
from app.trading import TradingEngine

SECRET='test-secret-that-is-at-least-thirty-two-characters'

def test_upbit_encrypted_and_plaintext_compatibility():
    row={'access_key':encrypt_upbit(SECRET,'owner','access'),'secret_key':encrypt_upbit(SECRET,'owner','secret')}
    assert row['access_key']!='access' and row['secret_key']!='secret'
    assert upbit_credentials(SECRET,'owner',row)==('access','secret')
    assert upbit_credentials(SECRET,'owner',{'access_key':'access','secret_key':'secret'})==('access','secret')
    with pytest.raises(HTTPException):upbit_credentials(SECRET,'other',row)

def test_private_key_boundary_decrypts_without_mutating_comparison_values(monkeypatch):
    monkeypatch.setenv('SESSION_SECRET',SECRET)
    engine=TradingEngine(None,'http://calculation',False)
    row={'user_login_id':'owner','access_key':encrypt_upbit(SECRET,'owner','access'),
         'secret_key':encrypt_upbit(SECRET,'owner','secret')}
    original=dict(row);calls=[]
    monkeypatch.setattr(engine,'private_upbit',lambda *args: calls.append(args))
    try:
        engine.private_for_key('GET','/v1/accounts',row)
        assert calls[0][2:4]==('access','secret') and row==original
    finally:engine.stop()

def test_startup_plaintext_conversion_is_atomic_and_idempotent():
    class Database:
        def __init__(self):self.rows=[{'id':1,'user_login_id':'owner','access_key':'access','secret_key':'secret'}];self.commits=0
        @contextmanager
        def connection(self):yield self;self.commits+=1
        @contextmanager
        def cursor(self):yield self
        def execute(self,sql,params=()):
            if sql.startswith('UPDATE'):
                self.rows[0]['access_key'],self.rows[0]['secret_key']=params[:2]
        def fetchall(self):return self.rows
    db=Database()
    assert migrate_upbit_credentials(db,SECRET)==1
    assert all(db.rows[0][field].startswith(PREFIX) for field in ('access_key','secret_key'))
    assert migrate_upbit_credentials(db,SECRET)==0 and db.commits==2


def test_key_save_encrypts_and_account_route_decrypts(monkeypatch):
    from app import main
    from fastapi.testclient import TestClient
    class Database:
        row=None
        def one(self,*args):return self.row
        def execute(self,sql,params):
            self.row={'user_login_id':params[0],'access_key':params[1],'secret_key':params[2]}
    db=Database();monkeypatch.setattr(main,'db',db)
    main.app.dependency_overrides[main.current_user]=lambda: {'id':1,'user_login_id':'owner'}
    calls=[]
    monkeypatch.setattr(main.engine,'account_snapshot',lambda *args: calls.append(args) or {'assets':[]})
    try:
        client=TestClient(main.app)
        assert client.put('/api/upbit/key',json={'access_key':'access','secret_key':'secret'}).status_code==200
        assert db.row['access_key'].startswith(PREFIX) and db.row['secret_key'].startswith(PREFIX)
        assert client.get('/api/upbit/accounts').status_code==200
        assert calls==[('access','secret')]
    finally:main.app.dependency_overrides.clear()


def test_ai_account_summary_uses_decrypted_key():
    from app.ai import AIService
    from app.main import SettingUpdate
    calls=[]
    class Database:
        def all(self,*args):return []
        def one(self,*args):return {'access_key':encrypt_upbit(SECRET,'owner','access'),
                                   'secret_key':encrypt_upbit(SECRET,'owner','secret')}
    class Engine:
        def private_upbit(self,*args):calls.append(args);return []
    service=AIService(lambda:Database(),Engine(),'http://calculation',SECRET,SettingUpdate)
    service._context({'market':'upbit','include_account':True,'settings_snapshot':{}},{'user_login_id':'owner'})
    assert calls[0][2:]==('access','secret')


@pytest.mark.parametrize('replaced',[False,True])
def test_auto_order_decrypts_but_key_replacement_checks_ciphertext(monkeypatch,replaced):
    monkeypatch.setenv('SESSION_SECRET',SECRET)
    row={'id':1,'user_login_id':'owner','access_key':encrypt_upbit(SECRET,'owner','access'),
         'secret_key':encrypt_upbit(SECRET,'owner','secret')}
    calls=[]
    class Database:
        def all(self,*args):return []
        def one(self,sql,params):
            assert params==(1,row['access_key'],row['secret_key'])
            return None if replaced else {'id':1}
        def execute(self,*args):pass
    engine=TradingEngine(Database(),'http://calculation',False)
    def private(method,path,access,secret,params=None):
        assert (access,secret)==('access','secret');calls.append(method)
        if path=='/v1/accounts':return [{'currency':'KRW','balance':'10000'}]
        if path=='/v1/orders/chance':return {'bid_fee':'0','market':{'bid':{'min_total':'5000'}}}
        return {'uuid':'test'}
    monkeypatch.setattr(engine,'private_upbit',private)
    monkeypatch.setattr(engine,'calc',lambda *_: {'actions':[{'side':'BUY','market':'KRW-BTC'}]})
    try:
        engine._auto_order_for_key(row,['KRW-BTC'])
        assert ('POST' in calls) is not replaced
    finally:engine.stop()
