from contextlib import contextmanager
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
