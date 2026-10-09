import hashlib
import threading
from contextlib import contextmanager
from urllib.parse import urlencode

import httpx
import jwt
import pytest

from app.trading import TradingEngine


def test_stop_waits_for_order_before_client_close(trading_engine, monkeypatch):
    closed = threading.Event()
    monkeypatch.setattr(trading_engine._upbit_client, 'close', closed.set)
    trading_engine._auto_order_lock.acquire()
    worker = threading.Thread(target=trading_engine.stop)
    worker.start()
    assert trading_engine._stopping.wait(1)
    assert not closed.wait(0.05)
    trading_engine._auto_order_lock.release()
    worker.join(1)
    assert closed.is_set() and not worker.is_alive()
    assert trading_engine.auto_order()['reason'] == 'stopping'


def test_stop_timeout_closes_client_and_warns(trading_engine, monkeypatch, caplog):
    closed = []
    monkeypatch.setattr(trading_engine._upbit_client, 'close', lambda: closed.append(True))
    trading_engine._auto_order_lock.acquire()
    try:
        trading_engine.stop(timeout=0.01)
        assert closed == [True]
        assert 'shutdown wait exceeded' in caplog.text
    finally:
        trading_engine._auto_order_lock.release()


@pytest.mark.parametrize('currency,balance,locked,expected', [
    ('OLD', '1', '0', {'OLD': 'unsupported'}),
    ('BTC', '0.001', '0', {'BTC': 'dust'}),
    ('BTC', '1', '0', {}),
    ('BTC', '0', '1', {}),
])
def test_unsellable_classification_preserves_locked_holdings(trading_engine, monkeypatch,
                                                           currency, balance, locked, expected):
    monkeypatch.setattr(trading_engine, 'upbit_public', lambda path, *args:
        [{'market': 'KRW-BTC', 'korean_name': '비트코인'}] if 'market/all' in path
        else [{'market': 'KRW-BTC', 'trade_price': 10000}])
    result = trading_engine.unsellable_balances([
        {'currency': currency, 'balance': balance, 'locked': locked}],
        lambda market: {'market': {'ask': {'min_total': '5000'}}})
    assert result == expected


@pytest.mark.parametrize('failure', ['market', 'ticker', 'chance'])
def test_unsellable_lookup_failure_preserves_holdings(trading_engine, monkeypatch, failure):
    def public(path, *args):
        if failure == ('market' if 'market/all' in path else 'ticker'):
            raise RuntimeError('unavailable')
        return ([{'market': 'KRW-BTC', 'korean_name': '비트코인'}] if 'market/all' in path
                else [{'market': 'KRW-BTC', 'trade_price': 1}])
    monkeypatch.setattr(trading_engine, 'upbit_public', public)
    def chance(market):
        raise RuntimeError('unavailable')
    assert trading_engine.unsellable_balances(
        [{'currency': 'BTC', 'balance': '1', 'locked': '0'}], chance) == {}


@pytest.mark.parametrize('currency,quantity,failed,expected_side', [
    ('OLD', '1', False, 'bid'), ('ETH', '0.001', False, 'bid'),
    ('ETH', '1', False, 'ask'), ('ETH', '0.001', True, 'ask'),
    ('ETH', '1', False, 'hold'),
])
def test_unsellable_balances_buy_or_preserve_sell(trading_engine, monkeypatch, caplog,
                                               currency, quantity, failed, expected_side):
    accounts = [{'currency': 'KRW', 'balance': '10000', 'locked': '0'},
                {'currency': currency, 'balance': quantity, 'locked': '0'}]
    submitted = []
    def public(path, *args):
        if failed:
            raise RuntimeError('market unavailable')
        return ([{'market': 'KRW-BTC', 'korean_name': '비트코인'},
                 {'market': 'KRW-ETH', 'korean_name': '이더리움'}] if 'market/all' in path
                else [{'market': 'KRW-BTC', 'trade_price': 10000},
                      {'market': 'KRW-ETH', 'trade_price': 10000}])
    def private(method, path, key, params=None):
        assert method == 'GET'
        if path == '/v1/accounts':
            return accounts
        assert path == '/v1/orders/chance'
        return {'bid_fee': '0.0005', 'ask_account': {'balance': quantity},
                'market': {'bid': {'min_total': '5000'}, 'ask': {'min_total': '5000'}}}
    def calculate(path, payload):
        held = [r['currency'] for r in payload['balances'] if r['currency'] != 'KRW']
        if held and f'KRW-{held[0]}' in payload['recommended_markets']:
            return {'actions': []}
        return {'actions': [{'market': f'KRW-{held[0]}', 'side': 'SELL'}] if held
                else [{'market': 'KRW-BTC', 'side': 'BUY'}]}
    monkeypatch.setattr(trading_engine, 'upbit_public', public)
    monkeypatch.setattr(trading_engine, 'private_for_key', private)
    monkeypatch.setattr(trading_engine, 'calc', calculate)
    monkeypatch.setattr(trading_engine, '_submit_auto_order',
                        lambda key, params: submitted.append(params) or {'uuid': 'mock'})
    monkeypatch.setattr(trading_engine, 'save_order', lambda *args: None)
    with caplog.at_level('INFO', logger='app.trading'):
        for _ in range(2):
            trading_engine._auto_order_for_key(trading_engine.db.keys[0],
                                             ['KRW-BTC', 'KRW-XRP',
                                              'KRW-ETH' if expected_side == 'hold' else 'KRW-SOL'])
    assert [p['side'] for p in submitted] == ([] if expected_side == 'hold'
                                             else [expected_side, expected_side])
    assert caplog.text.count('Unsellable holding excluded') == int(expected_side == 'bid')
    assert not any('trade_error_log' in sql for sql, _ in trading_engine.db.writes)


@pytest.mark.parametrize('currency,quantity,reason', [
    ('OLD', '1', 'unsupported'), ('BTC', '0.001', 'dust'), ('BTC', '1', None),
])
def test_snapshot_unsellable_badge_preserves_asset_valuation(trading_engine, monkeypatch,
                                                          currency, quantity, reason):
    monkeypatch.setattr(trading_engine, 'private_upbit', lambda method, path, *args:
        [{'currency': currency, 'balance': quantity, 'locked': '0',
          'avg_buy_price': '5000', 'unit_currency': 'KRW'}] if path == '/v1/accounts'
        else {'market': {'ask': {'min_total': '5000'}}})
    monkeypatch.setattr(trading_engine, 'upbit_public', lambda path, *args:
        [{'market': 'KRW-BTC', 'korean_name': '비트코인'}] if 'market/all' in path
        else [{'market': 'KRW-BTC', 'trade_price': 10000}])
    result = trading_engine.account_snapshot('test', 'test')
    assert len(result['assets']) == 1
    assert result['assets'][0]['unsellable_reason'] == reason
    assert result['total_valuation'] == (0 if currency == 'OLD' else float(quantity) * 10000)


def test_dust_btc_still_buys_first_recommended_btc(trading_engine, monkeypatch):
    accounts = [{'currency': 'KRW', 'balance': '10000', 'locked': '0'},
                {'currency': 'BTC', 'balance': '0.001', 'locked': '0'}]
    recommendations = ['KRW-BTC', 'KRW-ETH', 'KRW-SOL']
    submitted = []
    monkeypatch.setattr(trading_engine, 'upbit_public', lambda path, *args:
        [{'market': code, 'korean_name': code} for code in recommendations]
        if path == '/v1/market/all' else
        [{'market': code, 'trade_price': 10000} for code in recommendations])
    def private(method, path, key, params=None):
        assert method == 'GET'
        if path == '/v1/accounts':
            return accounts
        assert path == '/v1/orders/chance'
        return {'bid_fee': '0.0005', 'market': {
            'ask': {'min_total': '5000'}, 'bid': {'min_total': '5000'}}}
    def calculate(path, payload):
        assert path == '/v1/auto-trade/decide'
        assert payload['balances'] == [{'currency': 'KRW'}]
        assert payload['recommended_markets'] == recommendations
        return {'actions': [{'market': market, 'side': 'BUY'} for market in recommendations]}
    def submit(key, params):
        submitted.append(params)
        accounts[0]['balance'] = '0'
        return {'uuid': 'mock-btc-order'}
    monkeypatch.setattr(trading_engine, 'private_for_key', private)
    monkeypatch.setattr(trading_engine, 'calc', calculate)
    monkeypatch.setattr(trading_engine, '_submit_auto_order', submit)
    monkeypatch.setattr(trading_engine, 'save_order', lambda *args: None)
    trading_engine._auto_order_for_key(trading_engine.db.keys[0], recommendations)
    assert len(submitted) == 1
    assert submitted[0]['market'] == 'KRW-BTC'
    assert submitted[0]['side'] == 'bid'
    assert submitted[0]['price'] == '9995.0'


class NoopDatabase:
    def execute(self, *_):
        pass


class TradingDatabase:
    @contextmanager
    def connection(self):yield self

    @contextmanager
    def cursor(self):
        database=self
        class Cursor:
            def execute(self,sql,params=()):
                if sql.lstrip().startswith(('INSERT','UPDATE','DELETE')):database.execute(sql,params)
                else:database.queries.append((sql,params))
            def fetchone(self):return None
        yield Cursor()

    def __init__(self):
        self.queries = []
        self.writes = []
        self.keys = [
            {"id": 1, "user_login_id": "first", "access_key": "first", "secret_key": "test-secret"},
            {"id": 2, "user_login_id": "second", "access_key": "second", "secret_key": "test-secret"},
        ]
        self.active = True
        self.manual_sell_cooldowns = []

    def all(self, sql, params=()):
        self.queries.append((sql, params))
        if "SELECT code FROM upbit" in sql:
            return [{"code": "KRW-BTC"}]
        if "identifier LIKE 'manual-sell-%%'" in sql:
            return [{"market": market} for market in self.manual_sell_cooldowns]
        return self.keys

    def one(self, sql, params=()):
        self.queries.append((sql, params))
        return {"id": params[0]} if self.active else None

    def execute(self, sql, params=()):
        self.writes.append((sql, params))


@pytest.fixture
def trading_engine():
    engine = TradingEngine(TradingDatabase(), "http://calculation", False)
    yield engine
    engine.stop()


def test_history_targets_sync_before_collection_and_preserve_history(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine, 'upbit_public', lambda *args: [
        {'market':'KRW-BTC','korean_name':'비트코인'}, {'market':'BTC-ETH'}])
    collected=[]
    monkeypatch.setattr(trading_engine, '_save_history', lambda *args: collected.append(len(trading_engine.db.writes)))
    trading_engine._save_upbit_history()
    assert collected==[2]
    deactivate,restore=trading_engine.db.writes
    assert 'NOT (code=ANY(%s))' in deactivate[0] and deactivate[1][-1]==['KRW-BTC']
    assert 'deleted_at=NULL' in restore[0] and restore[1][-1]==['KRW-BTC']
    assert all('upbit_history_label' in sql and 'DELETE' not in sql for sql,_ in trading_engine.db.writes)


@pytest.mark.parametrize('response', [[], {}, [{'market':'BTC-ETH'}], [{'market':None}],
                                       [{'market':'KRW-BTC'}, {}]])
def test_invalid_market_list_preserves_history_targets(trading_engine, monkeypatch, response):
    monkeypatch.setattr(trading_engine, 'upbit_public', lambda *args: response)
    monkeypatch.setattr(trading_engine, '_save_history', lambda *args: pytest.fail('must not collect'))
    with pytest.raises(RuntimeError): trading_engine._save_upbit_history()
    assert trading_engine.db.writes==[]


def test_market_list_failure_preserves_history_targets(trading_engine, monkeypatch):
    def fail(*args): raise httpx.ConnectError('temporary failure')
    monkeypatch.setattr(trading_engine, 'upbit_public', fail)
    with pytest.raises(httpx.ConnectError): trading_engine._save_upbit_history()
    assert trading_engine.db.writes==[]


def test_active_market_404_does_not_disable_target(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine.db, 'all', lambda *args: [{'code':'KRW-BTC','name':'Bitcoin'}])
    monkeypatch.setattr(trading_engine.db, 'one', lambda *args: None)
    errors=[]
    monkeypatch.setattr(trading_engine, 'record_error', lambda *args: errors.append(args))
    def fail(*args):
        response=httpx.Response(404,request=httpx.Request('GET','https://api.upbit.com/v1/candles/days'))
        response.raise_for_status()
    trading_engine._save_history('upbit','upbit_history_label',fail)
    assert len(errors)==1 and trading_engine.db.writes==[]


def test_relisted_market_reuses_existing_history_label(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine, 'setting', lambda *args: {
        'highest_price_reference_days':60,'expected_low_percentage':-12,
        'expected_high_percentage':15,'is_volume_check':False})
    monkeypatch.setattr(trading_engine, 'upbit_public', lambda *args: [{'market':'KRW-BTC','korean_name':'비트코인'}])
    monkeypatch.setattr(trading_engine.db, 'one', lambda *args: {'id':123})
    monkeypatch.setattr(trading_engine, 'upbit_prices', lambda *args: [])
    monkeypatch.setattr(trading_engine, 'calc', lambda *args: {'selected_codes':[]})
    trading_engine._collect_upbit()
    assert len(trading_engine.db.writes)==2
    sql,params=trading_engine.db.writes[1]
    assert 'UPDATE upbit_history_label SET deleted_at=NULL' in sql
    assert params==('비트코인',123,'비트코인')


@pytest.mark.parametrize('response', [[], {}, [{'market':'BTC-ETH'}], [{'market':'KRW-BTC'}]])
def test_collect_invalid_list_keeps_recommendations(trading_engine, monkeypatch,response):
    monkeypatch.setattr(trading_engine,'setting',lambda *_: {})
    monkeypatch.setattr(trading_engine,'upbit_public',lambda *_: response)
    with pytest.raises(RuntimeError): trading_engine._collect_upbit()
    assert trading_engine.db.writes==[]


def test_collect_market_lookup_failure_keeps_recommendations(trading_engine,monkeypatch):
    monkeypatch.setattr(trading_engine,'setting',lambda *_: {})
    def fail(*args):raise httpx.ConnectError('temporary failure')
    monkeypatch.setattr(trading_engine,'upbit_public',fail)
    with pytest.raises(httpx.ConnectError):trading_engine._collect_upbit()
    assert trading_engine.db.writes==[]


def test_collect_unchanged_label_has_no_update(trading_engine,monkeypatch):
    monkeypatch.setattr(trading_engine,'setting',lambda *_: {
        'highest_price_reference_days':60,'expected_low_percentage':-12,
        'expected_high_percentage':15,'is_volume_check':False})
    monkeypatch.setattr(trading_engine,'upbit_public',lambda *_: [{'market':'KRW-BTC','korean_name':'비트코인'}])
    monkeypatch.setattr(trading_engine.db,'one',lambda *_: {'id':1,'name':'비트코인','deleted_at':None})
    monkeypatch.setattr(trading_engine,'upbit_prices',lambda *_: [])
    monkeypatch.setattr(trading_engine,'calc',lambda *_: {'selected_codes':[]})
    trading_engine._collect_upbit()
    assert len(trading_engine.db.writes)==1
    sql,params=trading_engine.db.writes[0]
    assert 'UPDATE upbit SET' in sql and params[-1]==['KRW-BTC']


@pytest.mark.parametrize('status,error_name,path,side', [
    (404,'market_not_found','/v1/orders/chance','BUY'),
    (400,'market_not_found','/v1/orders/chance','BUY'),
    (400,'market_not_found','/v1/orders','BUY'),
    (404,'market_not_found','/v1/orders/chance','SELL'),
    (401,'jwt_verification','/v1/orders/chance','BUY'),
    (403,'out_of_scope','/v1/orders','BUY'),
    (400,'insufficient_funds_bid','/v1/orders','BUY')])
def test_auto_missing_market_continues_but_auth_and_other_errors_stop(
        trading_engine,monkeypatch,status,error_name,path,side):
    calls=[];errors=[];saved=[]
    def private(method,endpoint,*args):
        params=args[-1] if isinstance(args[-1],dict) else {}
        calls.append((method,endpoint,params))
        if endpoint=='/v1/accounts': return [{'currency':'KRW','balance':'10000'}]
        if endpoint==path and params.get('market')=='KRW-BONK':
            httpx.Response(status,json={'error':{'name':error_name}},
                request=httpx.Request(method,'https://api.upbit.com'+endpoint)).raise_for_status()
        if endpoint=='/v1/orders/chance':return {'bid_fee':'0.0005','market':{'bid':{'min_total':'5000'}}}
        return {'uuid':'next'}
    monkeypatch.setattr(trading_engine,'private_upbit',private)
    monkeypatch.setattr(trading_engine,'record_error',lambda *args: errors.append(args))
    monkeypatch.setattr(trading_engine,'save_order',lambda *args: saved.append(args))
    monkeypatch.setattr(trading_engine,'calc',lambda *_: {'actions':[
        {'market':'KRW-BONK','side':side},{'market':'KRW-ETH','side':'BUY'}]})
    if status in (401,403) or error_name=='insufficient_funds_bid':
        with pytest.raises(httpx.HTTPStatusError):trading_engine._auto_order_for_key(trading_engine.db.keys[0],[])
        assert not saved
    else:
        trading_engine._auto_order_for_key(trading_engine.db.keys[0],[])
        assert len(saved)==1 and len(errors)==1
        posted=[params['market'] for method,_,params in calls if method=='POST']
        assert posted[-1]=='KRW-ETH'
        if side=='SELL':assert 'KRW-BONK' not in posted


def test_upbit_order_token_contains_matching_query_hash():
    params = {"market": "KRW-BTC", "side": "bid", "price": "5000", "ord_type": "price"}
    token = TradingEngine.token("access", "secret", params)
    claims = jwt.decode(token, "secret", algorithms=["HS256"])
    assert claims["access_key"] == "access"
    assert claims["query_hash"] == hashlib.sha512(urlencode(params).encode()).hexdigest()
    assert claims["query_hash_alg"] == "SHA512"


def test_upbit_token_hashes_array_parameters_without_url_encoding():
    params = {"uuids[]": ["first", "second"]}
    token = TradingEngine.token("access", "secret", params)
    claims = jwt.decode(token, "secret", algorithms=["HS256"])
    expected = "uuids[]=first&uuids[]=second"
    assert claims["query_hash"] == hashlib.sha512(expected.encode()).hexdigest()


def test_scheduler_is_off_until_explicitly_enabled():
    engine = TradingEngine(NoopDatabase(), "http://calculation", False)
    engine.start()
    assert engine.scheduler.running is False


def test_stock_parser_skips_invalid_rows(monkeypatch):
    payload = {"hasNext": False, "items": [{"closingPrice": "10000", "changePrice": "100",
        "openingPrice": "9000", "highPrice": "11000", "lowPrice": "8000", "tradingVolume": "123456"},
        {"closingPrice": None}]}
    response = type("Response", (), {"json": lambda self: payload, "raise_for_status": lambda self: None})()
    monkeypatch.setattr("app.trading.httpx.get", lambda *args, **kwargs: response)
    assert TradingEngine.stock_prices("000000", 2) == [{"close": 10000, "diff": 100, "open": 9000,
        "high": 11000, "low": 8000, "volume": 123456}]


def test_stock_universe_uses_named_columns(monkeypatch):
    body = """<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th></tr>
    <tr><td>테스트</td><td>코스피</td><td>1234</td></tr></table>""".encode()
    response = type("Response", (), {"content": body, "raise_for_status": lambda self: None})()
    monkeypatch.setattr("app.trading.httpx.get", lambda *args, **kwargs: response)
    assert TradingEngine.stock_universe() == [{"name": "테스트", "code": "001234"}]


def test_dividend_parser_reads_code_name_and_rate():
    body = """<table class='type_1'><tr><td class='frst'><a
      href='/item/main.naver?code=005930'>삼성전자</a></td><td>70,000</td><td>25.12</td>
      <td>1,500</td><td>2.14</td></tr><tr><td>빈 행</td></tr></table>"""
    assert TradingEngine.parse_dividend_page(body) == [
        {"code": "005930", "name": "삼성전자", "dividend_rate": 2.14}
    ]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_auto_order_isolates_failed_accounts_and_only_disables_auth_failures(trading_engine, monkeypatch, status):
    calls = []

    def private(method, path, access, secret, params=None):
        calls.append((method, path, access))
        assert method == "GET" and path == "/v1/accounts"
        if access == "first":
            response = httpx.Response(status, request=httpx.Request("GET", "https://api.upbit.com/v1/accounts"))
            response.raise_for_status()
        return []

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": []})
    result = trading_engine.auto_order()
    assert result == {"status": "PARTIAL", "completed_accounts": 1, "failed_accounts": 1}
    assert [call[2] for call in calls] == ["first", "second"]
    disabled = [params for sql, params in trading_engine.db.writes if "SET auto_on=false" in sql]
    assert disabled == ([(1, "first", "test-secret")] if status in (401, 403) else [])
    errors = [params for sql, params in trading_engine.db.writes if "trade_error_log" in sql]
    assert len(errors) == 1
    assert errors[0][:3] == ("UPBIT", "AUTO_ORDER_ACCOUNT_1", "HTTPStatusError")
    key_query = next(sql for sql, _ in trading_engine.db.queries if "SELECT k.*" in sql)
    assert "JOIN tb_user" in key_query
    assert "k.auto_on=true" in key_query and "u.deleted_at IS NULL" in key_query


def test_auto_order_isolates_non_http_errors(trading_engine, monkeypatch):
    calls = []

    def process(key, markets):
        calls.append(key["id"])
        if key["id"] == 1:
            raise ValueError("Invalid calculation response")

    monkeypatch.setattr(trading_engine, "_auto_order_for_key", process)
    result = trading_engine.auto_order()
    assert calls == [1, 2]
    assert result["failed_accounts"] == 1


def test_auto_order_buy_priority_matches_recommendation_sort(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine, "_auto_order_for_key", lambda *_: None)
    trading_engine.auto_order()
    query = next(sql for sql, _ in trading_engine.db.queries if "SELECT code FROM upbit" in sql)
    assert "renewal_cnt DESC" in query
    assert "expected_selling_price-temp_price" in query and "ASC NULLS LAST" in query
    assert "id DESC" in query


def test_auto_order_skips_overlapping_manual_and_scheduler_runs(trading_engine, monkeypatch):
    started, release = threading.Event(), threading.Event()
    results = []

    def process():
        started.set()
        assert release.wait(3)
        return {"status": "OK"}

    monkeypatch.setattr(trading_engine, "_auto_order", process)
    worker = threading.Thread(target=lambda: results.append(trading_engine.auto_order()))
    worker.start()
    try:
        assert started.wait(3)
        assert trading_engine.auto_order() == {"status": "SKIPPED", "reason": "already_running"}
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results == [{"status": "OK"}]
    assert not trading_engine._auto_order_lock.locked()


def test_auto_order_releases_lock_after_failure(trading_engine, monkeypatch):
    def fail():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(trading_engine, "_auto_order", fail)
    assert trading_engine.auto_order() == {"status": "ERROR"}
    assert not trading_engine._auto_order_lock.locked()
    monkeypatch.setattr(trading_engine, "_auto_order", lambda: {"status": "OK"})
    assert trading_engine.auto_order() == {"status": "OK"}


def test_job_run_preserves_successful_none_result(trading_engine):
    assert trading_engine.run("STOCK", "SCHEDULE_UPDATE", lambda: None) is None
    assert trading_engine.db.writes == []


def test_job_run_returns_failure_status_and_records_original_error(trading_engine):
    def fail():
        raise ValueError("Invalid upstream data")

    assert trading_engine.run("STOCK", "SCHEDULE_UPDATE", fail) == {"status": "ERROR"}
    sql, params = trading_engine.db.writes[0]
    assert "INSERT INTO trade_error_log" in sql
    assert params[:4] == ("STOCK", "SCHEDULE_UPDATE", "ValueError", "Invalid upstream data")


@pytest.mark.parametrize("active", [True, False])
def test_order_checks_current_permission_and_keeps_existing_buy_amount(trading_engine, monkeypatch, active):
    calls, saved = [], []
    trading_engine.db.active = active

    def private(method, path, access, secret, params=None):
        calls.append((method, path, params))
        if path == "/v1/accounts":
            return [{"currency": "KRW", "balance": "10000", "locked": "0"}]
        if path == "/v1/orders/chance":
            return {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}}}
        assert method == "POST" and path == "/v1/orders"
        return {"uuid": "mock-order"}

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": [{"market": "KRW-BTC", "side": "BUY"}]})
    monkeypatch.setattr(trading_engine, "save_order", lambda *args: saved.append(args))
    trading_engine._auto_order_for_key(trading_engine.db.keys[0], ["KRW-BTC"])
    orders = [params for method, _, params in calls if method == "POST"]
    assert len(orders) == int(active)
    assert len(saved) == int(active)
    permission_query, params = trading_engine.db.queries[-1]
    assert "k.auto_on=true" in permission_query and "u.deleted_at IS NULL" in permission_query
    assert "k.access_key=%s AND k.secret_key=%s" in permission_query
    assert params == (1, "first", "test-secret")
    if active:
        assert orders[0]['identifier'].startswith('auto-1-KRW-BTC-BUY-')
        assert {k:v for k,v in orders[0].items() if k!='identifier'} == {"market": "KRW-BTC", "side": "bid", "price": "9995.0", "ord_type": "price"}


def test_auto_order_skips_recent_manual_sell_and_buys_next_ranked_market(trading_engine, monkeypatch):
    calls, saved = [], []
    trading_engine.db.manual_sell_cooldowns = ["KRW-BTC"]

    def private(method, path, access, secret, params=None):
        calls.append((method, path, params))
        if path == "/v1/accounts":
            return [{"currency": "KRW", "balance": "10000", "locked": "0"}]
        if path == "/v1/orders/chance":
            assert params == {"market": "KRW-ETH"}
            return {"bid_fee": "0.0005", "market": {"bid": {"min_total": "5000"}}}
        assert method == "POST" and params["market"] == "KRW-ETH"
        return {"uuid": "next-ranked-order"}

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": [
        {"market": "KRW-BTC", "side": "BUY"}, {"market": "KRW-ETH", "side": "BUY"},
    ]})
    monkeypatch.setattr(trading_engine, "save_order", lambda *args: saved.append(args))

    trading_engine._auto_order_for_key(trading_engine.db.keys[0], ["KRW-BTC", "KRW-ETH", "KRW-XRP"])

    posted = [params for method, path, params in calls if method == "POST" and path == "/v1/orders"]
    assert len(posted) == 1 and posted[0]["market"] == "KRW-ETH"
    assert saved
    cooldown_query = next(sql for sql, _ in trading_engine.db.queries if "manual-sell-%%" in sql)
    assert "created_at::timestamptz" in cooldown_query and "CASE" in cooldown_query


def test_sell_skips_zero_available_balance(trading_engine, monkeypatch):
    calls = []

    def private(method, path, access, secret, params=None):
        calls.append(method)
        assert method == "GET"
        if path == "/v1/accounts":
            return [{"currency": "BTC", "balance": "0", "locked": "1"}]
        return {"ask_account": {"balance": "0"}}

    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "calc", lambda *_: {"actions": [{"market": "KRW-BTC", "side": "SELL"}]})
    trading_engine._auto_order_for_key(trading_engine.db.keys[0], [])
    assert calls == ["GET", "GET"]


def test_manual_market_sell_rechecks_balance_keeps_auto_and_never_sends_price(trading_engine, monkeypatch):
    calls, saved = [], []
    key = trading_engine.db.keys[0]
    def private(method, path, access, secret, params=None):
        calls.append((method, path, params))
        if path == "/v1/orders/chance":
            return {"ask_account": {"balance": "0.25"},
                    "market": {"ask": {"min_total": "5000"}, "ask_types": ["limit", "market"]}}
        assert method == "POST" and path == "/v1/orders"
        return {"uuid": "sell-uuid", "state": "wait"}
    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "upbit_public", lambda *_: [{"trade_price": "100000"}])
    monkeypatch.setattr(trading_engine, "save_order", lambda *args: saved.append(args))
    result = trading_engine.manual_market_sell(key, "KRW-BTC", "0.25")
    order = calls[-1][2]
    assert result["uuid"] == "sell-uuid" and result["history_saved"] is True
    assert order["side"] == "ask" and order["ord_type"] == "market" and order["volume"] == "0.25"
    assert "price" not in order and order["identifier"].startswith("manual-sell-1-")
    assert saved and not any("SET auto_on=false" in sql for sql, _ in trading_engine.db.writes)
    assert not trading_engine._auto_order_lock.locked()


@pytest.mark.parametrize("expected,price,message", [
    ("0.24", "100000", "변경"), ("0.25", "1000", "최소 매도금액"),
])
def test_manual_market_sell_rejects_stale_or_too_small_order(trading_engine, monkeypatch, expected, price, message):
    calls = []
    def private(method, path, *args, **kwargs):
        calls.append(method)
        return {"ask_account": {"balance": "0.25"},
                "market": {"ask": {"min_total": "5000"}, "ask_types": ["market"]}}
    monkeypatch.setattr(trading_engine, "private_upbit", private)
    monkeypatch.setattr(trading_engine, "upbit_public", lambda *_: [{"trade_price": price}])
    with pytest.raises(ValueError, match=message):
        trading_engine.manual_market_sell(trading_engine.db.keys[0], "KRW-BTC", expected)
    assert calls == ["GET"] and not trading_engine._auto_order_lock.locked()


def test_account_snapshot_preserves_unknown_prices_and_non_krw_costs(trading_engine, monkeypatch):
    accounts = [
        {"currency": "KRW", "balance": "5000", "locked": "1000", "avg_buy_price": "0", "unit_currency": "KRW"},
        {"currency": "BTC", "balance": "1", "locked": "1", "avg_buy_price": "10000", "unit_currency": "KRW"},
        {"currency": "OLD", "balance": "2", "locked": "0", "avg_buy_price": "50", "unit_currency": "KRW"},
        {"currency": "ETH", "balance": "3", "locked": "0", "avg_buy_price": "0.01", "unit_currency": "BTC"},
        {"currency": "ZERO", "balance": "0", "locked": "0", "avg_buy_price": "5", "unit_currency": "KRW"},
    ]
    monkeypatch.setattr(trading_engine, "private_upbit", lambda *_: accounts)
    monkeypatch.setattr(trading_engine, "upbit_public", lambda *_: [
        {"market": "KRW-BTC", "trade_price": 12000}, {"market": "KRW-ETH", "trade_price": 1000},
    ])
    result = trading_engine.account_snapshot("test", "test")
    assert result["total_valuation"] == 33000
    assert result["valuation_complete"] is False
    assert result["unpriced_currencies"] == ["OLD"]
    assert [row["currency"] for row in result["assets"]] == ["BTC", "KRW", "ETH", "OLD"]
    by_currency = {row["currency"]: row for row in result["assets"]}
    assert by_currency["BTC"]["profit_rate"] == 20
    assert by_currency["BTC"]["quantity"] == 2
    assert by_currency["OLD"]["current_price"] is None
    assert by_currency["OLD"]["valuation"] is None
    assert by_currency["OLD"]["profit_rate"] is None
    assert by_currency["ETH"]["purchase_amount"] is None
    assert by_currency["ETH"]["profit_rate"] is None


def test_order_fills_returns_trades_list_and_tolerates_missing_detail(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine, "private_upbit",
                        lambda *_, **__: {"uuid": "order-1", "trades": [{"price": "100", "volume": "2", "funds": "200"}]})
    assert trading_engine.order_fills("access", "secret", "order-1") == [{"price": "100", "volume": "2", "funds": "200"}]

    monkeypatch.setattr(trading_engine, "private_upbit", lambda *_, **__: {"uuid": "order-2"})
    assert trading_engine.order_fills("access", "secret", "order-2") == []


def test_empty_account_snapshot_is_complete(trading_engine, monkeypatch):
    monkeypatch.setattr(trading_engine, "private_upbit", lambda *_: [])
    monkeypatch.setattr(trading_engine, "upbit_public", lambda *_: [])
    assert trading_engine.account_snapshot("test", "test") == {
        "total_valuation": 0, "valuation_complete": True, "unpriced_currencies": [], "assets": [],
    }


@pytest.mark.parametrize("all_failed", [False, True])
def test_recommendation_quote_failures_do_not_block_other_positions(trading_engine, monkeypatch, all_failed):
    template = {"name": "Test", "expected_selling_price": 120, "minimum_selling_price": 90,
                "temp_price": 100, "setting_price": 100, "renewal_cnt": 0}
    monkeypatch.setattr(trading_engine, "setting", lambda *_: {"expected_high_percentage": 10, "expected_low_percentage": -5})
    monkeypatch.setattr(trading_engine.db, "all", lambda *_: [{**template, "code": "BAD"}, {**template, "code": "GOOD"}])
    requests, errors = [], []
    monkeypatch.setattr(trading_engine, "record_error", lambda *args: errors.append(args))
    def quotes(code, count):
        if code == "BAD" or all_failed:
            raise httpx.ConnectError("test quote failure")
        return [{"close": 110, "high": 112, "low": 105, "volume": 1}]
    def calculate(endpoint, payload):
        requests.append(payload)
        return {"positions": []}
    monkeypatch.setattr(trading_engine, "calc", calculate)
    trading_engine._update_positions("upbit", quotes)
    assert len(errors) == (2 if all_failed else 1)
    assert errors[0][:2] == ("UPBIT", "UPDATE_PRICE_ITEM")
    if all_failed:
        assert not requests
    else:
        assert [p["code"] for p in requests[0]["positions"]] == ["GOOD"]
