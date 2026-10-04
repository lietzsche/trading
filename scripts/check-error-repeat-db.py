"""Only for the disposable, isolated repeat_test PostgreSQL database."""
import os
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from app.trading import TradingEngine

DSN=os.environ['ERROR_REPEAT_TEST_DSN']
class TestDB:
    @contextmanager
    def connection(self):
        with psycopg.connect(DSN,row_factory=dict_row) as connection:
            if connection.info.dbname!='repeat_test':raise RuntimeError('Test DB only')
            yield connection
    def all(self,sql,params=()):
        with self.connection() as connection:return connection.execute(sql,params).fetchall()
    def execute(self,sql,params=()):
        with self.connection() as connection:connection.execute(sql,params)

db=TestDB()
db.execute('''CREATE TABLE trade_error_log(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source varchar(20),operation varchar(100),error_type varchar(255),message text,created_at varchar(255))''')
migration=Path('/migration.sql').read_text()
db.execute(migration);db.execute(migration)
engine=TradingEngine(db,'http://unused',False)
try:
    engine.record_error('UPBIT','FETCH_PRICE',ValueError('first representative'))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i:engine.record_error('UPBIT','FETCH_PRICE',ValueError(f'coin {i}')),range(99)))
    rows=db.all('SELECT * FROM trade_error_log')
    assert len(rows)==1 and rows[0]['repeat_count']==100 and rows[0]['message']=='first representative'
    db.execute("UPDATE trade_error_log SET last_seen_at=to_char(clock_timestamp()-interval '11 minutes','YYYY-MM-DD HH24:MI:SS.US')")
    engine.record_error('UPBIT','FETCH_PRICE',ValueError('new window'))
    assert [row['repeat_count'] for row in db.all('SELECT * FROM trade_error_log ORDER BY id')]==[100,1]
    db.execute("UPDATE trade_error_log SET created_at='2000-01-01 00:00:00',last_seen_at=to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US') WHERE id=1")
    engine.prune_errors();assert len(db.all('SELECT * FROM trade_error_log'))==2
    db.execute("UPDATE trade_error_log SET created_at='2000-01-01 00:00:00',last_seen_at='2000-01-01 00:00:00' WHERE id=2")
    assert engine.prune_errors()['expired']==1
    assert db.all('SELECT id FROM trade_error_log')[0]['id']==1
    engine.error_max_records=100
    db.execute("""INSERT INTO trade_error_log(source,operation,error_type,message,created_at,last_seen_at)
        SELECT 'TEST','OLD_GROUP','ValueError','fixture','2000-01-01 00:00:00',
        to_char(clock_timestamp()-interval '2 days','YYYY-MM-DD HH24:MI:SS.US') FROM generate_series(1,120)""")
    pruned=engine.prune_errors()
    assert pruned['expired']==0 and pruned['excess']==21
    assert len(db.all('SELECT id FROM trade_error_log'))==100
    assert any(row['id']==1 for row in db.all('SELECT id FROM trade_error_log'))
    print('PASS: V010 twice; 100 concurrent occurrences = 1 row/count 100; expired window creates row; last-seen retention preserves active old group.')
finally:engine.stop()
