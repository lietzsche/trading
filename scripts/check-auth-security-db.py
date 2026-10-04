"""Run only against the disposable PostgreSQL security-check container."""
import os
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException
from app.auth_security import authenticate

DSN=os.environ['AUTH_SECURITY_TEST_DSN']
class Database:
    @contextmanager
    def connection(self):
        with psycopg.connect(DSN,row_factory=dict_row) as connection:
            if not connection.execute("SELECT to_regclass('security_test_marker') AS marker").fetchone()['marker']:
                raise RuntimeError('Disposable test database only')
            yield connection
db=Database()
def fail(_):return authenticate(db,'test-user','192.0.2.1',lambda:None)
with ThreadPoolExecutor(max_workers=5) as pool:
    assert list(pool.map(fail,range(5)))==[None]*5
for verify in (lambda:None,lambda:{'id':1}):
    try:authenticate(db,'test-user','192.0.2.1',verify)
    except HTTPException as error:assert error.status_code==429
    else:raise AssertionError('Locked user authenticated')
with db.connection() as connection:
    rows=connection.execute('SELECT failures FROM auth_attempts').fetchall()
    assert len(rows)==2 and all(row['failures']==5 for row in rows)
    connection.execute("UPDATE auth_attempts SET locked_until=now()-interval '1 second'")
assert authenticate(Database(),'test-user','192.0.2.1',lambda:{'id':1})=={'id':1}
with db.connection() as connection:
    assert connection.execute("SELECT count(*) AS count FROM auth_attempts WHERE scope='id'").fetchone()['count']==0
print('PASS: concurrent failures=5, both scopes persisted, sixth/valid locked=429, expiry success, ID reset')
