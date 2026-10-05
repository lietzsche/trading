from contextlib import contextmanager
import os
os.environ.setdefault('SESSION_SECRET','test-secret-that-is-at-least-thirty-two-characters')
os.environ.setdefault('SESSION_COOKIE_SECURE','false')
from datetime import datetime,timedelta,timezone
import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import main,auth_security

class AuthDB:
    def __init__(self):
        self.rows={};self.version=0;self.writes=[]
        self.password=bcrypt.hashpw(b'password123',bcrypt.gensalt()).decode()
    @contextmanager
    def connection(self):yield self
    @contextmanager
    def cursor(self):yield self
    def execute(self,sql,params=()):
        self.writes.append((sql,params));self.result=None
        if sql.startswith('SELECT * FROM auth_attempts'):self.result=self.rows.get(params)
        elif sql.startswith('INSERT INTO auth_attempts'):
            scope,subject,failures,start,until=params
            self.rows[(scope,subject)]={'failures':failures,'window_started_at':start,'locked_until':until}
        elif sql.startswith('DELETE FROM auth_attempts'):self.rows.pop(('id',params[0]),None)
        elif sql.startswith('UPDATE tb_user SET session_version'):self.version+=1
        elif 'user_password=COALESCE' in sql:
            if params[3]:self.password=params[3];self.version+=1
    def fetchone(self):return self.result
    def one(self,sql,params=()):
        if 'SELECT id FROM tb_user' in sql:return None
        if 'tb_user' in sql:
            return {'id':1,'user_login_id':'master','user_name':'Master','user_role':'MASTER',
                    'user_password':self.password,'session_version':self.version}
        return None

@pytest.fixture
def auth(monkeypatch):
    database=AuthDB();monkeypatch.setattr(main,'db',database)
    main.app.dependency_overrides.clear()
    client=TestClient(main.app,raise_server_exceptions=True)
    try:yield database,client
    finally:client.close()

def test_signup_disabled_and_enabled(auth,monkeypatch):
    db,client=auth;payload={'login_id':'newuser','name':'New','password':'password123'}
    monkeypatch.setattr(main,'SIGNUP_ENABLED',False)
    assert client.get('/api/auth/config').json()=={'signup_enabled':False}
    assert client.post('/api/auth/join',json=payload).status_code==403
    monkeypatch.setattr(main,'SIGNUP_ENABLED',True)
    assert client.post('/api/auth/join',json=payload).status_code==201

def test_fifth_failure_locks_sixth_and_valid_password_until_expiry(auth,monkeypatch):
    db,client=auth
    for _ in range(5):assert client.post('/api/auth/login',json={'login_id':'master','password':'wrong'}).status_code==401
    for password in ('wrong','password123'):
        assert client.post('/api/auth/login',json={'login_id':'master','password':password}).status_code==429
    # Simulate restart by retaining only DB state, then expire both locks.
    for row in db.rows.values():row['locked_until']=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert client.post('/api/auth/login',json={'login_id':'master','password':'password123'}).status_code==200
    assert ('id','master') not in db.rows

def test_ip_scope_blocks_different_login_ids(auth):
    db,client=auth
    for index in range(5):assert client.post('/api/auth/login',json={'login_id':f'unknown{index}','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'login_id':'master','password':'password123'}).status_code==429


def test_ip_lock_does_not_lock_same_id_from_other_ip_before_twenty_failures():
    db=AuthDB()
    for _ in range(5):
        assert auth_security.authenticate(db,'master','192.0.2.1',lambda:None) is None
    with pytest.raises(HTTPException) as error:
        auth_security.authenticate(db,'master','192.0.2.1',lambda:{'id':1})
    assert error.value.status_code==429
    assert db.rows[('id','master')]['failures']==5
    assert db.rows[('id','master')]['locked_until'] is None
    assert auth_security.authenticate(db,'master','192.0.2.2',lambda:{'id':1})=={'id':1}
    assert ('id','master') not in db.rows
    assert db.rows[('ip','192.0.2.1')]['locked_until'] is not None


def test_twenty_id_failures_lock_all_ips():
    db=AuthDB()
    for index in range(20):
        assert auth_security.authenticate(db,'master',f'192.0.2.{index+1}',lambda:None) is None
    assert db.rows[('id','master')]['failures']==20
    for ip in ('192.0.2.1','198.51.100.1'):
        with pytest.raises(HTTPException) as error:
            auth_security.authenticate(db,'master',ip,lambda:{'id':1})
        assert error.value.status_code==429

def test_logout_invalidates_previous_cookie(auth):
    db,client=auth
    assert client.post('/api/auth/login',json={'login_id':'master','password':'password123'}).status_code==200
    cookie=client.cookies.get('session')
    assert client.post('/api/auth/logout').status_code==204
    client.cookies.set('session',cookie)
    assert client.get('/api/auth/me').status_code==401

@pytest.mark.parametrize('current',[None,'wrong'])
def test_password_change_requires_correct_current_password(auth,current):
    db,client=auth
    client.post('/api/auth/login',json={'login_id':'master','password':'password123'})
    response=client.put('/api/profile',json={'name':'Master','password':'newpassword123','current_password':current})
    assert response.status_code==400 and db.version==0

def test_password_change_invalidates_session(auth):
    db,client=auth
    client.post('/api/auth/login',json={'login_id':'master','password':'password123'})
    assert client.put('/api/profile',json={'name':'Master','password':'newpassword123','current_password':'password123'}).status_code==200
    assert client.get('/api/auth/me').status_code==401


@pytest.mark.parametrize('peer,header,expected',[
    ('127.0.0.1','203.0.113.5','203.0.113.5'),
    ('172.18.0.1','203.0.113.6','203.0.113.6'),
    ('203.0.113.7','203.0.113.8','203.0.113.7'),
    ('127.0.0.1','invalid','127.0.0.1')])
def test_cloudflare_address_is_trusted_only_from_connector(monkeypatch,peer,header,expected):
    from starlette.requests import Request
    from fastapi import Response
    calls=[]
    def authenticate(db,login_id,ip,verify):
        calls.append(ip);return {'user_login_id':'master','user_name':'Master','user_role':'MASTER'}
    monkeypatch.setattr(main,'authenticate',authenticate)
    request=Request({'type':'http','client':(peer,1),'headers':[(b'cf-connecting-ip',header.encode())]})
    main.login(main.LoginRequest(login_id='master',password='password123'),Response(),request)
    assert calls==[expected]
