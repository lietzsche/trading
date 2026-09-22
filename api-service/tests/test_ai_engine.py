"""Every network request is intercepted; these tests never spend API credit."""

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.ai_engine import (
    AIAnalysisError, DEEPSEEK_URL, MAX_OUTPUT_TOKENS, NEWS_RSS_URL, _MarketData, _NewsData,
    _candidate_settings, _price, _settings, analyze, continue_analysis,
)


CURRENT = {"expected_high_percentage": 10, "expected_low_percentage": -5,
           "highest_price_reference_days": 60, "volume_check": False}
ALTERNATIVE = {**CURRENT, "expected_high_percentage": 12}


def candles(code="KRW-BTC", count=200):
    today = datetime.now(timezone.utc).date()
    return [{"market": code, "candle_date_time_utc": f"{today - timedelta(days=index + 1)}T00:00:00",
             "opening_price": 100 + index, "high_price": 110 + index,
             "low_price": 90 + index, "trade_price": 105 + index,
             "candle_acc_trade_volume": 1000} for index in range(count)]


def completion(report="완료 일봉을 참고한 설정 검토입니다.", candidates=None, tool_calls=None, actions=None):
    if actions is None:
        actions = [{"code": "KRW-BTC", "action": "WATCH", "reason": "추가 확인이 필요합니다.",
                    "evidence": [], "confidence": 50}]
    message = {"role": "assistant", "content": json.dumps({
        "report": report, "candidates": candidates if candidates is not None else [{"label": "대안", "settings": ALTERNATIVE}],
        "portfolio_actions": actions,
    }, ensure_ascii=False)}
    if tool_calls is not None:
        message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
    return {"choices": [{"message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}


def chat_completion(answer="추가 조사 답변입니다.", tool_calls=None):
    message = ({"role": "assistant", "content": json.dumps({"answer": answer}, ensure_ascii=False)}
               if tool_calls is None else {"role": "assistant", "content": None, "tool_calls": tool_calls})
    return {"choices": [{"message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
            "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120}}


def malformed_completion(content="이것은 JSON이 아닙니다."):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def tool(code="KRW-ETH", name="get_market_history", arguments=None):
    return {"id": "call-1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments if arguments is not None else {"code": code, "count": 200}),
    }}


@pytest.fixture
def network(monkeypatch):
    requests, responses, comparison_payloads = [], [], []
    state = {"responses": responses, "data_status": 200, "comparison_status": 200, "search_payloads": []}
    real_client = httpx.Client

    def handler(request):
        requests.append(request)
        if request.url.host == "api.upbit.com":
            assert request.method == "GET"
            assert request.url.path == "/v1/candles/days"
            assert "authorization" not in request.headers
            return httpx.Response(state["data_status"], json=candles(request.url.params["market"]))
        if str(request.url) == DEEPSEEK_URL:
            assert request.method == "POST"
            assert request.headers["authorization"] == "Bearer test-only-key"
            payload = json.loads(request.content)
            assert payload["max_tokens"] == MAX_OUTPUT_TOKENS
            assert payload["thinking"] == {"type": "disabled"}
            assert payload["stream"] is False
            reply = responses.pop(0) if responses else completion()
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json=reply)
        if str(request.url).startswith(NEWS_RSS_URL):
            assert request.method == "GET" and "authorization" not in request.headers
            body = """<?xml version='1.0'?><rss><channel><item><title>시장 소식</title>
                <link>https://news.google.com/rss/articles/test</link><pubDate>Sun, 13 Sep 2026 01:00:00 GMT</pubDate>
                <source>테스트 언론</source></item></channel></rss>"""
            return httpx.Response(200, content=body.encode())
        if request.url.host == "calculation":
            assert request.method == "POST" and "authorization" not in request.headers
            payload = json.loads(request.content)
            if request.url.path == "/v1/backtests/search":
                state["search_payloads"].append(payload)
                space = payload["search_space"]
                combinations = (len(space["expected_high_percentage"]["values"]) * len(space["expected_low_percentage"]["values"])
                                * len(space["highest_price_reference_days"]["values"]) * len(space["volume_check"]))
                return httpx.Response(200, json={
                    "top_candidates": [{"id": "search-0", "label": "탐색 조합 1",
                                        "settings": {**CURRENT, "expected_high_percentage": space["expected_high_percentage"]["values"][0]},
                                        "train": {"return_pct": 3.0}, "validation": {"return_pct": 1.5, "trades": 6}}],
                    "combinations_evaluated": combinations, "combinations_eligible": 1,
                    "minimum_validation_trades": 5, "warnings": [], "dataset": {"validation_days": 42}, "limitations": [],
                })
            assert request.url.path == "/v1/backtests/compare"
            comparison_payloads.append(payload)
            return httpx.Response(state["comparison_status"], json={
                "candidates": [{"id": item["id"], "label": item["label"],
                                "settings": {key: item[key] for key in CURRENT},
                                "train": {"return_pct": 2.5}, "validation": {"return_pct": -1.2}}
                               for item in payload["candidates"]],
                "warnings": [], "dataset": {"validation_days": 42},
            })
        raise AssertionError(f"Unexpected network destination: {request.method} {request.url}")

    monkeypatch.setattr("app.ai_engine.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr("app.ai_engine.time.sleep", lambda _: None)
    return state, requests, comparison_payloads


def run(**overrides):
    arguments = {"api_key": "test-only-key", "model": "deepseek-flash", "market": "upbit",
                 "prompt": "현재 설정의 위험을 알려 주세요.", "context": {"settings": CURRENT},
                 "symbols": ["KRW-BTC"], "fee_bps": 5, "slippage_bps": 10,
                 "remaining_tokens": 500_000, "calculation_url": "http://calculation"}
    return analyze(**{**arguments, **overrides})


def test_analyze_includes_current_and_same_closed_dataset_for_all_candidates(network):
    state, requests, payloads = network
    result = run()
    assert [item["id"] for item in result["candidates"]] == ["current", "candidate-1"]
    assert result["candidates"][0]["settings"] == CURRENT
    assert result["usage_tokens"] == 150
    assert result["prompt_tokens"] == 100 and result["completion_tokens"] == 50
    assert result["dataset"]["validation_days"] == 42
    assert len(payloads) == 1 and len(payloads[0]["instruments"][0]["prices"]) == 200
    prices = payloads[0]["instruments"][0]["prices"]
    assert prices == sorted(prices, key=lambda item: item["date"])
    assert all(item["date"] < datetime.now(timezone.utc).date().isoformat() for item in prices)
    assert len(requests) == 3


def test_tools_cache_symbol_and_use_all_additional_data_in_single_comparison(network):
    state, requests, payloads = network
    state["responses"] += [completion(tool_calls=[tool()]), completion(tool_calls=[tool()]), completion()]
    result = run()
    public = [request for request in requests if request.url.host == "api.upbit.com"]
    assert len(public) == 2
    assert {item["code"] for item in payloads[0]["instruments"]} == {"KRW-BTC", "KRW-ETH"}
    assert result["usage_tokens"] == 450
    assert [item["status"] for item in result["tool_calls"]] == ["OK", "OK"]


@pytest.mark.parametrize("call", [tool(name="place_order"), tool(code="https://evil.example"),
                                 tool(arguments={"code": "KRW-BTC", "url": "https://evil.example"}),
                                 tool(code="005930"), tool(arguments={"code": "KRW-BTC", "count": 201})])
def test_untrusted_tools_cannot_request_orders_urls_other_markets_or_oversized_counts(network, call):
    state, requests, _ = network
    state["responses"] += [completion(tool_calls=[call]), completion()]
    result = run()
    assert result["tool_calls"] == [{"name": call["function"]["name"],
                                      "code": call["function"]["name"] == "get_market_history" and json.loads(call["function"]["arguments"]).get("code") == "KRW-BTC" and "KRW-BTC" or None,
                                      "status": "UNAVAILABLE"}]
    assert len([request for request in requests if request.url.host == "api.upbit.com"]) == 1


def test_maximum_four_tool_calls_then_forced_final_answer(network):
    state, requests, _ = network
    state["responses"] += [completion(tool_calls=[tool()]) for _ in range(4)] + [completion()]
    result = run()
    provider = [json.loads(request.content) for request in requests if str(request.url) == DEEPSEEK_URL]
    assert len(provider) == 5
    assert provider[-1]["tool_choice"] == "none"
    assert len(result["tool_calls"]) == 4


def test_excessive_tool_calls_fail_without_executing_them(network):
    state, requests, _ = network
    state["responses"] += [completion(tool_calls=[tool() for _ in range(5)])]
    with pytest.raises(AIAnalysisError, match="한도") as caught:
        run()
    assert caught.value.consumed_tokens == 150 and caught.value.request_started
    assert len([request for request in requests if request.url.host == "api.upbit.com"]) == 1


def test_maximum_five_distinct_symbols_including_initial_symbols(network):
    state, requests, payloads = network
    decisions = [{"code": code, "action": "WATCH", "reason": "추가 확인이 필요합니다.",
                  "evidence": [], "confidence": 50} for code in ("KRW-BTC", "KRW-ETH", "KRW-XRP")]
    state["responses"] += [completion(tool_calls=[tool("KRW-DOGE"), tool("KRW-ADA"), tool("KRW-SOL")]),
                           completion(actions=decisions)]
    result = run(symbols=["KRW-BTC", "KRW-ETH", "KRW-XRP"])
    assert len([request for request in requests if request.url.host == "api.upbit.com"]) == 5
    assert len(payloads[0]["instruments"]) == 5
    assert result["tool_calls"][-1]["status"] == "UNAVAILABLE"


def test_budget_preflight_prevents_any_paid_call(network):
    _, requests, _ = network
    with pytest.raises(AIAnalysisError, match="토큰") as caught:
        run(remaining_tokens=100)
    assert caught.value.consumed_tokens == 0 and not caught.value.request_started
    assert not any(str(request.url) == DEEPSEEK_URL for request in requests)


def test_initial_analysis_can_use_bounded_rss_news_tool(network):
    state, requests, _ = network
    news_call = tool(name="search_market_news", arguments={"query": "비트코인 시장", "count": 3})
    state["responses"] += [completion(tool_calls=[news_call]), completion()]
    result = run()
    assert result["tool_calls"] == [{"name": "search_market_news", "query": "비트코인 시장", "count": 1, "status": "OK"}]
    assert any(source.get("provider") == "Google News RSS" for source in result["data_sources"])
    assert len([request for request in requests if request.url.host == "news.google.com"]) == 1


def test_analyze_retries_once_on_malformed_final_json(network):
    state, requests, _ = network
    state["responses"] += [malformed_completion(), completion()]
    result = run()
    assert result["candidates"][0]["id"] == "current"
    provider = [request for request in requests if str(request.url) == DEEPSEEK_URL]
    assert len(provider) == 2


def test_analyze_retries_when_portfolio_decision_is_missing(network):
    state, requests, _ = network
    state["responses"] += [completion(actions=[]), completion(actions=[{"code": "KRW-BTC", "action": "HOLD",
        "reason": "추세가 유지됩니다.", "evidence": ["완료 일봉"], "confidence": 60}])]
    result = run()
    assert result["portfolio_actions"][0]["action"] == "HOLD"
    provider = [request for request in requests if str(request.url) == DEEPSEEK_URL]
    assert len(provider) == 2


def test_analyze_fails_after_two_malformed_final_replies(network):
    state, requests, _ = network
    state["responses"] += [malformed_completion(), malformed_completion()]
    with pytest.raises(AIAnalysisError, match="형식"):
        run()
    provider = [request for request in requests if str(request.url) == DEEPSEEK_URL]
    assert len(provider) == 2


def test_follow_up_keeps_context_and_can_research_news(network):
    state, requests, _ = network
    news_call = tool(name="search_market_news", arguments={"query": "삼성전자 실적", "count": 5})
    state["responses"] += [chat_completion(tool_calls=[news_call]), chat_completion("뉴스 제목만 기준으로 보면 추가 확인이 필요합니다.")]
    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="stock",
        question="최근 뉴스도 확인해 줘", analysis_context={"report": "기존 분석"},
        prior_messages=[{"question": "위험은?", "answer": "변동성입니다."}], symbols=["005930"],
        remaining_tokens=500_000, calculation_url="http://calculation",
        instrument_catalog=[{"code": "005930", "name": "삼성전자"}])
    assert "추가 확인" in result["answer"] and result["usage_tokens"] == 240
    assert result["data_sources"][0]["articles"][0]["source"] == "테스트 언론"
    provider_payload = next(json.loads(request.content) for request in requests if str(request.url) == DEEPSEEK_URL)
    assert "기존 분석" in provider_payload["messages"][1]["content"]


def test_follow_up_retries_once_on_malformed_final_json(network):
    state, requests, _ = network
    state["responses"] += [malformed_completion(), chat_completion("정상 재시도 답변입니다.")]
    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="stock",
        question="다시 물어볼게요", analysis_context={"report": "기존 분석"},
        prior_messages=[], symbols=["005930"], remaining_tokens=500_000,
        calculation_url="http://calculation", instrument_catalog=[{"code": "005930", "name": "삼성전자"}])
    assert result["answer"] == "정상 재시도 답변입니다."
    provider = [request for request in requests if str(request.url) == DEEPSEEK_URL]
    assert len(provider) == 2


def test_follow_up_can_backtest_requested_settings_without_mutation(network):
    state, requests, payloads = network
    backtest_call = tool(name="compare_strategy_settings", arguments={"settings": ALTERNATIVE})
    state["responses"] += [chat_completion(tool_calls=[backtest_call]), chat_completion("검증 구간 결과를 비교했습니다.")]

    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="upbit",
        question="이 설정으로 백테스트해 줘", analysis_context={
            "report": "기존 분석", "request": {"fee_bps": 7, "slippage_bps": 12}},
        prior_messages=[], symbols=["KRW-BTC"], remaining_tokens=500_000,
        calculation_url="http://calculation",
        instrument_catalog=[{"code": "KRW-BTC", "name": "비트코인"}])

    assert result["tool_calls"] == [{"name": "compare_strategy_settings", "symbols": 1, "status": "OK"}]
    assert payloads[-1]["candidates"][0]["expected_high_percentage"] == 12
    assert payloads[-1]["fee_bps"] == 7 and payloads[-1]["slippage_bps"] == 12
    assert any(request.url.host == "api.upbit.com" for request in requests)


def test_follow_up_can_search_a_bounded_grid_of_strategy_settings(network):
    state, requests, _ = network
    search_call = tool(name="search_strategy_settings", arguments={
        "expected_high_percentage_values": [10, 20], "expected_low_percentage_values": [-5, -10],
        "highest_price_reference_days_values": [60],
    })
    state["responses"] += [chat_completion(tool_calls=[search_call]), chat_completion("탐색 결과를 검토했습니다.")]

    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="upbit",
        question="여러 설정 조합 중 더 나은 값을 찾아줘", analysis_context={"report": "기존 분석"},
        prior_messages=[], symbols=["KRW-BTC"], remaining_tokens=500_000,
        calculation_url="http://calculation",
        instrument_catalog=[{"code": "KRW-BTC", "name": "비트코인"}])

    assert result["tool_calls"] == [{"name": "search_strategy_settings", "symbols": 1,
                                     "combinations_evaluated": 8, "status": "OK"}]  # 2 highs * 2 lows * 1 day * 2 default volume_check values
    assert state["search_payloads"][-1]["search_space"]["expected_high_percentage"]["values"] == [10, 20]
    assert state["search_payloads"][-1]["search_space"]["volume_check"] == [False, True]
    assert any(request.url.host == "api.upbit.com" for request in requests)


def test_search_strategy_settings_rejects_missing_required_axis(network):
    state, requests, _ = network
    bad_call = tool(name="search_strategy_settings", arguments={"expected_high_percentage_values": [10]})
    state["responses"] += [chat_completion(tool_calls=[bad_call]), chat_completion("설명입니다.")]

    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="upbit",
        question="설정 조합을 찾아줘", analysis_context={"report": "기존 분석"},
        prior_messages=[], symbols=["KRW-BTC"], remaining_tokens=500_000,
        calculation_url="http://calculation",
        instrument_catalog=[{"code": "KRW-BTC", "name": "비트코인"}])

    assert result["tool_calls"] == [{"name": "search_strategy_settings", "status": "UNAVAILABLE"}]
    assert not any(request.url.host == "calculation" for request in requests)


def test_follow_up_can_search_statistics_and_consented_portfolio(network):
    state, _, _ = network
    calls = [
        tool(name="search_instruments", arguments={"query": "비트", "count": 5}),
        tool(name="get_market_statistics", arguments={"code": "KRW-BTC", "count": 120}),
        tool(name="get_portfolio_context", arguments={}),
    ]
    for index, call in enumerate(calls):
        call["id"] = f"call-{index}"
    state["responses"] += [chat_completion(tool_calls=calls), chat_completion("동의한 계좌와 통계를 함께 검토했습니다.")]
    portfolio = {"accounts": [{"currency": "KRW", "balance": "10000"}],
                 "recent_orders": [{"market": "KRW-BTC", "side": "bid", "state": "done"}]}

    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="upbit",
        question="내 거래와 비트코인 상태를 같이 봐줘", analysis_context={"report": "기존 분석"},
        prior_messages=[], symbols=["KRW-BTC"], remaining_tokens=500_000,
        calculation_url="http://calculation",
        instrument_catalog=[{"code": "KRW-BTC", "name": "비트코인"}],
        portfolio_context=portfolio)

    assert [item["name"] for item in result["tool_calls"]] == [
        "search_instruments", "get_market_statistics", "get_portfolio_context"]
    assert all(item["status"] == "OK" for item in result["tool_calls"])
    assert result["data_sources"][0]["code"] == "KRW-BTC"


def test_portfolio_tool_is_unavailable_without_per_message_consent(network):
    state, _, _ = network
    state["responses"] += [chat_completion(tool_calls=[tool(name="get_portfolio_context", arguments={})]), chat_completion()]
    result = continue_analysis(api_key="test-only-key", model="deepseek-flash", market="upbit",
        question="내 계좌 봐줘", analysis_context={"report": "기존 분석"}, prior_messages=[],
        symbols=["KRW-BTC"], remaining_tokens=500_000, calculation_url="http://calculation",
        instrument_catalog=[{"code": "KRW-BTC", "name": "비트코인"}])
    assert result["tool_calls"] == [{"name": "get_portfolio_context", "status": "UNAVAILABLE"}]


def test_news_reader_rejects_entities_and_non_google_links(monkeypatch):
    responses = [b"<!DOCTYPE rss [<!ENTITY x 'bad'>]><rss/>",
                 b"<rss><channel><item><title>x</title><link>https://evil.example/a</link></item></channel></rss>"]
    def handler(_):
        return httpx.Response(200, content=responses.pop(0))
    monkeypatch.setattr("app.ai_engine.time.sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="안전"):
            _NewsData(client, 10**20).search("시장 뉴스")
        assert _NewsData(client, 10**20).search("시장 뉴스")["articles"] == []


def test_unknown_usage_after_provider_timeout_is_conservatively_accounted(network):
    state, _, _ = network
    state["responses"] += [httpx.ReadTimeout("test-only-key sensitive provider text")]
    with pytest.raises(AIAnalysisError) as caught:
        run()
    assert "test-only-key" not in str(caught.value)
    assert caught.value.consumed_tokens > MAX_OUTPUT_TOKENS
    assert caught.value.request_started


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500])
def test_provider_failures_redact_secret_and_do_not_retry_paid_calls(network, status):
    state, requests, _ = network
    state["responses"] += [httpx.Response(status, text="test-only-key sensitive backend response")]
    with pytest.raises(AIAnalysisError) as caught:
        run()
    assert "test-only-key" not in str(caught.value)
    assert "sensitive" not in str(caught.value)
    assert len([request for request in requests if str(request.url) == DEEPSEEK_URL]) == 1


def test_invalid_final_response_preserves_consumed_tokens(network):
    state, _, _ = network
    reply = completion()
    reply["choices"][0]["message"]["content"] = "not json; test-only-key"
    # Both the first reply and the retry are malformed, so the retry cannot save it.
    state["responses"] += [reply, reply]
    with pytest.raises(AIAnalysisError) as caught:
        run()
    assert caught.value.consumed_tokens == 300
    assert "test-only-key" not in str(caught.value)


def test_missing_usage_records_reserved_tokens(network):
    state, _, _ = network
    reply = completion()
    reply.pop("usage")
    state["responses"] += [reply]
    result = run()
    assert result["usage_tokens"] > MAX_OUTPUT_TOKENS
    assert any("사용량" in warning for warning in result["warnings"])


def test_backtest_unavailable_returns_honest_unverified_candidates(network):
    state, _, _ = network
    state["comparison_status"] = 422
    result = run()
    assert all(item["train"] is None and item["validation"] is None for item in result["candidates"])
    assert result["candidates"][0]["id"] == "current"
    assert any("30개" in warning for warning in result["warnings"])


def test_candidate_settings_are_validated_deduplicated_and_capped():
    warnings = []
    parsed = {"report": "key secret-value", "candidates": [
        {"label": "현재중복", "settings": CURRENT},
        {"label": "잘못된상한", "settings": {**CURRENT, "expected_high_percentage": 0}},
        {"label": "secret-value", "settings": ALTERNATIVE},
        {"label": "네번째무시", "settings": {**ALTERNATIVE, "volume_check": True}},
    ]}
    report, candidates, actions = _candidate_settings(parsed, "secret-value", CURRENT, warnings)
    assert "secret-value" not in report
    assert len(candidates) == 2 and len(warnings) == 1 and actions == []
    assert candidates[1]["label"] == "[비밀키 삭제]"


def test_portfolio_actions_are_explicit_owner_safe_and_redacted():
    warnings = []
    parsed = {"report": "결론", "candidates": [], "portfolio_actions": [
        {"code": "KRW-BTC", "action": "SELL", "reason": "secret-value 근거", "evidence": ["손절선 이탈"], "confidence": 82},
        {"code": "KRW-ETH", "action": "BUY", "reason": "허용되지 않은 행동", "confidence": 90},
        {"code": "KRW-XRP", "action": "HOLD", "reason": "분석하지 않은 종목", "confidence": 70},
    ]}
    _, _, actions = _candidate_settings(parsed, "secret-value", CURRENT, warnings, ["KRW-BTC", "KRW-ETH"])
    assert actions == [{"code": "KRW-BTC", "action": "SELL", "reason": "[비밀키 삭제] 근거",
                        "evidence": ["손절선 이탈"], "confidence": 82}]
    assert len(warnings) == 2


def test_portfolio_action_normalizes_provider_format_without_losing_decision():
    parsed = {"report": "결론", "candidates": [], "portfolio_actions": [{
        "code": "KRW-BTC", "action": "HOLD", "reason": "근거가 있습니다.",
        "evidence": ["가" * 300, "둘", "셋", "넷", 123], "confidence": 72.6,
    }]}
    _, _, actions = _candidate_settings(parsed, "test-only-key", CURRENT, [], ["KRW-BTC"])
    assert actions[0]["action"] == "HOLD" and actions[0]["confidence"] == 73
    assert len(actions[0]["evidence"]) == 3 and len(actions[0]["evidence"][0]) == 250


def test_analysis_returns_validated_portfolio_decision(network):
    state, _, _ = network
    state["responses"] += [completion(actions=[{"code": "KRW-BTC", "action": "HOLD",
        "reason": "완료 일봉상 추세가 유지됩니다.", "evidence": ["20일 이동평균 상단"], "confidence": 65}])]
    result = run()
    assert result["portfolio_actions"][0]["action"] == "HOLD"
    assert result["portfolio_actions"][0]["confidence"] == 65


@pytest.mark.parametrize("change", [{"expected_high_percentage": 0}, {"expected_low_percentage": -100},
                                  {"highest_price_reference_days": 201}, {"volume_check": "false"},
                                  {"expected_high_percentage": True}, {"expected_low_percentage": 10}])
def test_invalid_settings_rejected(change):
    with pytest.raises(ValueError):
        _settings({**CURRENT, **change})


@pytest.mark.parametrize("changes", [{"market": "other"}, {"symbols": ["BTCUSDT"]},
                                   {"symbols": ["KRW-BTC"] * 6}, {"fee_bps": float("nan")},
                                   {"slippage_bps": -1}, {"model": "../../evil"}])
def test_invalid_inputs_make_no_network_calls(network, changes):
    _, requests, _ = network
    with pytest.raises(AIAnalysisError):
        run(**changes)
    assert requests == []


@pytest.mark.parametrize("values", [
    ("2026-09-13", 10, 12, 8, 11, 100),
    ("2026-09-12", 10, float("inf"), 8, 11, 100),
    ("2026-09-12", 10, 9, 8, 11, 100),
    ("2026-09-12", 10, 12, 11, 11, 100),
    ("2026-09-12", 10, 12, 8, 11, -1),
    ("not-date", 10, 12, 8, 11, 100),
])
def test_invalid_and_in_progress_candles_rejected(values):
    assert _price(*values, date(2026, 9, 13)) is None


def test_stock_parser_keeps_dates_deduplicates_and_drops_today(monkeypatch):
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    yesterday = today - timedelta(days=1)
    requests = []
    row = "<tr><td>{}</td><td>105</td><td>0</td><td>100</td><td>110</td><td>90</td><td>1,000</td></tr>"
    body = "<table class='type2'>" + row.format(today.strftime("%Y.%m.%d")) + row.format(yesterday.strftime("%Y.%m.%d")) * 2 + "</table>"
    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.host == "finance.naver.com"
        return httpx.Response(200, text=body)
    monkeypatch.setattr("app.ai_engine.time.sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = _MarketData(client, "stock", 10**20)
        result = data.history("005930")
        assert result["count"] == 1 and result["prices"][0]["date"] == yesterday.isoformat()
        assert len(requests) == 2
        assert data.history("005930")["count"] == 1
        assert len(requests) == 2


def test_public_429_retries_once_but_418_never_retries(monkeypatch):
    monkeypatch.setattr("app.ai_engine.time.sleep", lambda _: None)
    for status, expected in [(429, 2), (418, 1)]:
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(status, headers={"Retry-After": "9000"})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            data = _MarketData(client, "upbit", 10**20)
            with pytest.raises((httpx.HTTPError, AIAnalysisError)):
                data.history("KRW-BTC")
        assert len(requests) == expected


def test_no_public_data_never_spends_ai_credit(network):
    state, requests, _ = network
    state["data_status"] = 418
    with pytest.raises(AIAnalysisError, match="일봉") as caught:
        run()
    assert caught.value.consumed_tokens == 0
    assert not any(str(request.url) == DEEPSEEK_URL for request in requests)
