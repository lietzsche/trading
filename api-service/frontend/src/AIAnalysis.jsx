import React, {useCallback, useEffect, useRef, useState} from 'react';
import {api, createRequestGate} from './api';
import {AI_SETTING_FIELDS, AI_STATUS_LABELS, candidateEligible, isAnalysisRunning, parseAnalysisSymbols, percentText, sameSettings, settingText, textItems} from './ai';
import './ai.css';
import './ai-chat.css';

const API = '/admin/ai';
const count = value => Number(value || 0).toLocaleString('ko-KR');
const timestamp = value => value ? String(value).replace('T', ' ').slice(0, 16) : '—';
const marketName = value => value === 'upbit' ? 'Upbit' : '주식';
const defaults = {model: 'deepseek-flash'};

export function Metrics({title, values}) {
  return <div className="ai-metrics"><h4>{title}</h4><dl>
    <div><dt>과거 수익률</dt><dd>{percentText(values?.return_pct)}</dd></div>
    <div><dt>최대 낙폭</dt><dd>{percentText(values?.max_drawdown_pct)}</dd></div>
    <div><dt>청산 완료 거래</dt><dd>{values?.trades == null ? '—' : `${count(values.trades)}회`}</dd></div>
  </dl>{values?.days != null && <small>비교한 일봉 {count(values.days)}개</small>}{(values?.start_date || values?.end_date) && <small>{values.start_date || '—'} ~ {values.end_date || '—'}</small>}</div>;
}

export function AIReport({report}) {
  return <article className="ai-chat-assistant ai-first-answer"><b>DeepSeek</b><p className="ai-prose">{typeof report === 'string' ? report : '분석 설명이 없습니다.'}</p></article>;
}

function Dataset({dataset}) {
  if (!dataset) return null;
  return <section className="card ai-dataset"><h3>검증에 사용한 조건</h3><dl className="ai-setting-list">
    <div><dt>탐색 구간 · {count(dataset.train_days)}개 일봉</dt><dd>{dataset.train_start || '—'} ~ {dataset.train_end || '—'}</dd></div>
    <div><dt>검증 구간 · {count(dataset.validation_days)}개 일봉</dt><dd>{dataset.validation_start || '—'} ~ {dataset.validation_end || '—'}</dd></div>
    <div><dt>편도 수수료</dt><dd>{percentText(dataset.fee_bps == null ? null : dataset.fee_bps / 100)}</dd></div>
    <div><dt>편도 체결 가격 차이</dt><dd>{percentText(dataset.slippage_bps == null ? null : dataset.slippage_bps / 100)}</dd></div>
  </dl><p className="hint">공통 준비 기간 {count(dataset.warmup_days)}개 일봉은 수익률 비교에서 제외합니다. 아래 수치는 이 구간과 비용 가정에만 해당합니다.</p></section>;
}

function InstrumentResults({items}) {
  if (!Array.isArray(items) || !items.length) return null;
  return <details className="ai-details"><summary>종목별 비교 결과</summary><div className="ai-instruments">{items.map(item => <div key={item.code}><b>{item.name || item.code}{item.name && <small> {item.code}</small>}</b><span>탐색 {percentText(item.train?.return_pct)} · 검증 {percentText(item.validation?.return_pct)}</span><span>검증 최대 낙폭 {percentText(item.validation?.max_drawdown_pct)} · 청산 {item.validation?.trades == null ? '—' : `${count(item.validation.trades)}회`}</span></div>)}</div></details>;
}

function Notes({title, items}) {
  const visible = textItems(items);
  if (!visible.length) return null;
  return <section className="ai-notes"><h4>{title}</h4><ul>{visible.map((item, index) => <li key={index}>{item}</li>)}</ul></section>;
}

export default function AIAnalysis({user, refreshToken = 0, setError}) {
  const [config, setConfig] = useState(null), [configDraft, setConfigDraft] = useState(defaults), [apiKey, setApiKey] = useState('');
  const [history, setHistory] = useState({items: [], total: 0, page: 0, page_size: 10}), [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState(null), [selected, setSelected] = useState(null), [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(true), [pending, setPending] = useState(''), [notice, setNotice] = useState(''), [localError, setLocalError] = useState('');
  const [market, setMarket] = useState('upbit'), [prompt, setPrompt] = useState('현재 전략과 설정을 점검하고, 과거 데이터로 비교한 설정 후보의 장단점과 위험을 설명해 주세요.');
  const [symbols, setSymbols] = useState(''), [includeAccount, setIncludeAccount] = useState(false), [feeBps, setFeeBps] = useState(5), [slippageBps, setSlippageBps] = useState(10);
  const [recommendations, setRecommendations] = useState([]), [chatQuestion, setChatQuestion] = useState('');
  const [proposal, setProposal] = useState(null), [confirmed, setConfirmed] = useState(false), [detailVersion, setDetailVersion] = useState(0), [showEvidence, setShowEvidence] = useState(false);
  const mounted = useRef(false), operation = useRef(false), pageRef = useRef(page), previousPage = useRef(page), errorHandler = useRef(setError), selectedIdRef = useRef(selectedId), chatPanelRef = useRef(null);
  const listRequests = useRef(createRequestGate()), detailRequests = useRef(createRequestGate());
  pageRef.current = page; errorHandler.current = setError; selectedIdRef.current = selectedId;

  const showError = useCallback(error => {
    if (!mounted.current || error?.name === 'AbortError') return;
    if (error?.status === 401) {errorHandler.current?.(error); return;}
    setLocalError(error?.message || String(error));
  }, []);

  const refresh = useCallback(async (resetDraft = false) => {
    const request = listRequests.current.begin();
    setLoading(true);
    try {
      const [nextConfig, nextHistory] = await Promise.all([
        api(`${API}/config`, {signal: request.signal}),
        api(`${API}/analyses?page=${pageRef.current}`, {signal: request.signal}),
      ]);
      if (!request.isCurrent()) return;
      setConfig(nextConfig); setHistory(nextHistory);
      if (selectedIdRef.current === null && nextHistory.items?.length) setSelectedId(nextHistory.items[0].id);
      if (resetDraft) setConfigDraft({model: nextConfig.model || defaults.model});
    } catch (error) {if (request.isCurrent()) showError(error);}
    finally {if (request.isCurrent()) setLoading(false);}
  }, [showError]);

  useEffect(() => {
    mounted.current = true;
    return () => {mounted.current = false; listRequests.current.cancel(); detailRequests.current.cancel();};
  }, []);

  useEffect(() => {refresh(true);}, [refresh, refreshToken]);
  useEffect(() => {if (previousPage.current !== page) {previousPage.current = page; refresh(false);}}, [refresh, page]);
  useEffect(() => {
    const controller = new AbortController();
    api(`${API}/recommendations/${market}`, {signal: controller.signal}).then(rows => {if (!controller.signal.aborted) setRecommendations(Array.isArray(rows) ? rows : []);}).catch(error => {if (error?.name !== 'AbortError') setRecommendations([]);});
    return () => controller.abort();
  }, [market, refreshToken]);

  useEffect(() => {
    if (selectedId === null) return;
    const request = detailRequests.current.begin();
    let timer;
    setDetailLoading(true);
    async function poll() {
      try {
        const result = await api(`${API}/analyses/${encodeURIComponent(selectedId)}`, {signal: request.signal});
        if (!request.isCurrent()) return;
        setSelected(result); setDetailLoading(false);
        if (isAnalysisRunning(result.status) || result.conversations?.some(item => isAnalysisRunning(item.status))) timer = setTimeout(poll, 3000);
        else refresh(false);
      } catch (error) {if (request.isCurrent()) {setDetailLoading(false); showError(error);}}
    }
    poll();
    return () => {clearTimeout(timer); detailRequests.current.cancel();};
  }, [selectedId, detailVersion, refreshToken, refresh, showError]);

  async function runAction(name, action) {
    if (operation.current) return;
    operation.current = true; setPending(name); setNotice(''); setLocalError('');
    try {await action();} catch (error) {showError(error);}
    finally {operation.current = false; if (mounted.current) setPending('');}
  }

  function selectAnalysis(id) {
    detailRequests.current.cancel(); setSelected(null); setSelectedId(id); setProposal(null); setConfirmed(false); setShowEvidence(false); setLocalError('');
    if (id === selectedId) setDetailVersion(value => value + 1);
  }

  async function saveConfig(event) {
    event.preventDefault();
    await runAction('config', async () => {
      const body = {...configDraft};
      if (apiKey.trim()) body.api_key = apiKey.trim();
      await api(`${API}/config`, {method: 'PUT', body: JSON.stringify(body)});
      if (!mounted.current) return;
      setApiKey(''); setNotice('AI 연결 설정을 저장했습니다. 연결 확인은 저장된 키를 사용합니다.'); await refresh(true);
    });
  }

  async function startAnalysis(event) {
    event.preventDefault();
    await runAction('analysis', async () => {
      const parsed = parseAnalysisSymbols(symbols, market);
      const result = await api(`${API}/analyses`, {method: 'POST', body: JSON.stringify({market, prompt: prompt.trim(), include_account: market === 'upbit' && includeAccount, symbols: parsed, fee_bps: Number(feeBps), slippage_bps: Number(slippageBps)})});
      if (!mounted.current) return;
      setPage(0); selectAnalysis(result.id); setNotice('분석을 시작했습니다. 페이지를 나가도 서버에서 계속 진행됩니다.'); await refresh(false);
    });
  }

  function toggleSymbol(code) {
    try {
      const current = parseAnalysisSymbols(symbols, market), exists = current.includes(code);
      const next = exists ? current.filter(item => item !== code) : [...current, code];
      if (next.length > 5) throw new Error('종목은 최대 5개까지 선택할 수 있습니다.');
      setSymbols(next.join(', ')); setLocalError('');
    } catch (error) {showError(error);}
  }

  async function askFollowUp(event) {
    event.preventDefault();
    const question = chatQuestion.trim();
    if (!question || selectedId == null) return;
    await runAction('chat', async () => {
      await api(`${API}/analyses/${encodeURIComponent(selectedId)}/messages`, {method: 'POST', body: JSON.stringify({question})});
      if (!mounted.current) return;
      setChatQuestion(''); setNotice('메시지를 보냈습니다. 필요한 경우 시세와 RSS 뉴스를 조회합니다.');
      setDetailVersion(value => value + 1); await refresh(false);
    });
  }

  async function deleteConversation() {
    const deletingId = selectedId;
    if (deletingId == null || !window.confirm('이 AI 대화와 모든 메시지를 삭제할까요? 복구할 수 없습니다.')) return;
    await runAction('delete-chat', async () => {
      await api(`${API}/analyses/${encodeURIComponent(deletingId)}`, {method: 'DELETE'});
      if (!mounted.current) return;
      detailRequests.current.cancel(); selectedIdRef.current = null; setSelectedId(null); setSelected(null);
      setProposal(null); setShowEvidence(false); setNotice('AI 대화를 삭제했습니다.'); await refresh(false);
    });
  }

  async function inspectCandidate(candidate) {
    const analysisId = selectedId;
    await runAction(`inspect-${candidate.id}`, async () => {
      const settings = await api('/admin/settings');
      if (!mounted.current || selectedIdRef.current !== analysisId) return;
      const current = settings.find(item => item.name === selected.market);
      if (!current) throw new Error('현재 계산 설정을 확인할 수 없어 적용을 중단했습니다.');
      setProposal({candidate, current, analysisId}); setConfirmed(false);
    });
  }

  async function applyCandidate() {
    if (!proposal || !confirmed) return;
    const applying = proposal;
    await runAction('apply', async () => {
      await api(`${API}/analyses/${encodeURIComponent(applying.analysisId)}/apply`, {method: 'POST', body: JSON.stringify({candidate_id: applying.candidate.id, confirm: true})});
      if (!mounted.current) return;
      setProposal(null); setConfirmed(false); setNotice('계산 설정을 적용했습니다. 다음 계산부터 반영되며 자동매매 켜짐/꺼짐 상태는 변경하지 않습니다.'); setDetailVersion(value => value + 1);
    });
  }

  const conversations = Array.isArray(selected?.conversations) ? selected.conversations : [];
  const chatRunning = conversations.some(item => isAnalysisRunning(item.status));
  const running = isAnalysisRunning(selected?.status), used = config?.usage_today || {};
  const pages = Math.max(1, Math.ceil(history.total / (history.page_size || 10)));
  const result = selected?.result || {}, candidates = Array.isArray(result.candidates) ? result.candidates : [];
  const selectedSymbols = (() => {try {return parseAnalysisSymbols(symbols, market);} catch {return [];}})();
  const master = user.user_role === 'MASTER';
  const stale = Boolean(proposal && !sameSettings(proposal.current, selected?.settings_snapshot));

  useEffect(() => {
    if (!selected || !chatPanelRef.current) return;
    chatPanelRef.current.scrollTo({top: chatPanelRef.current.scrollHeight, behavior: conversations.length ? 'smooth' : 'auto'});
  }, [selectedId, conversations.length, conversations.at(-1)?.status]);

  return <div className="ai-page">
    <section className="ai-intro"><div><span className="eyebrow">AI MARKET CHAT</span><h2>시장 분석을 대화로<br/>이어가세요.</h2><p>주식·Upbit 종목을 고르고 질문하면 DeepSeek가 시세와 RSS 뉴스를 조사해 같은 대화에서 답합니다. 검증된 설정만 별도 승인할 수 있습니다.</p></div><span className="ai-mode">조회·대화 전용</span></section>
    {localError && <div className="error" role="alert">{localError}<button className="quiet compact" onClick={() => {setLocalError(''); refresh(false); setDetailVersion(value => value + 1);}}>다시 조회</button></div>}
    {notice && <div className="notice" role="status">{notice}</div>}
    <div className="info-note"><b>수익 예측이 아닌 과거 데이터 검증입니다.</b><span>종목별 독립·동일 비중으로 계산하는 단순 시뮬레이션이며 실제 자동매매 전체를 재현하지 않습니다. 수수료와 가격 차이를 반영해도 미체결·유동성·미래 시장 변동은 보장할 수 없습니다. 실제 수익을 약속하지 않습니다.</span></div>

    <details className="card ai-config" open={!config?.configured || undefined}>
      <summary><span>DeepSeek 연결 설정</span><span className={`status-pill ${config?.configured ? 'on' : 'off'}`}>{config?.configured ? '키 등록됨' : '키 등록 필요'}</span></summary>
      <form className="form" onSubmit={saveConfig}>
        <p className="hint">내 계정의 키와 분석 기록만 사용합니다. 키는 서버에 암호화해 저장하며 다시 표시하지 않습니다. Upbit 비밀키·로그인 비밀번호는 AI에 보내지 않습니다.</p>
        <label>DeepSeek API 키<input type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} autoComplete="new-password" maxLength={255} placeholder={config?.configured ? '변경할 때만 새 키 입력' : 'DeepSeek API 키 입력'} required={!config?.configured}/>{config?.key_hint && <small>등록된 키: {config.key_hint}</small>}</label>
        <div className="ai-form-grid ai-one"><label>분석 모델<select value={configDraft.model} onChange={event => setConfigDraft({...configDraft, model: event.target.value})}><option value="deepseek-flash">DeepSeek Flash</option>{configDraft.model !== 'deepseek-flash' && <option value={configDraft.model}>{configDraft.model}</option>}</select></label></div>
        <div className="ai-actions"><button className="primary" disabled={Boolean(pending) || loading}>{pending === 'config' ? '저장 중…' : '연결 설정 저장'}</button><button type="button" className="quiet" disabled={!config?.configured || Boolean(pending)} onClick={() => runAction('test', async () => {await api(`${API}/config/test`, {method: 'POST'}); if (mounted.current) setNotice('저장된 API 키로 연결을 확인했습니다. 분석 요청은 실행하지 않았습니다.');})}>{pending === 'test' ? '확인 중…' : '저장된 키 연결 확인'}</button><button type="button" className="danger" disabled={!config?.configured || Boolean(pending)} onClick={() => {if (window.confirm('저장된 DeepSeek API 키를 삭제할까요? 새 분석에는 키를 다시 등록해야 합니다.')) runAction('delete', async () => {await api(`${API}/config`, {method: 'DELETE'}); if (mounted.current) {setApiKey(''); setNotice('DeepSeek API 키를 삭제했습니다.'); await refresh(true);}});}}>키 삭제</button></div>
      </form>
    </details>

    <section className="ai-usage" aria-label="오늘의 AI 사용량"><span>오늘 AI 요청 <b>{count(used.runs)}회</b></span><span>오늘 사용량 <b>{count(used.tokens)} 토큰</b></span><span>한 답변의 자료 조회 <b>최대 {config?.max_tool_calls || 4}회</b></span><small>앱 자체의 일일 대화 제한은 없습니다. DeepSeek 계정의 잔액·속도·사용 한도를 따르며, 각 요청은 안전을 위해 최대 실행 시간과 출력 길이만 제한합니다.</small></section>

    {selectedId === null && <section className="card ai-new-chat"><div className="section-head ai-section-head"><h3>새 분석 대화</h3><span className="ai-muted">첫 메시지와 함께 백테스트를 시작합니다</span></div><form className="form" onSubmit={startAnalysis}>
      <div className="ai-form-grid ai-two"><label>시장<select value={market} onChange={event => {setMarket(event.target.value); setSymbols(''); setIncludeAccount(false); setFeeBps(event.target.value === 'upbit' ? 5 : 15);}}><option value="upbit">Upbit · 원화 마켓</option><option value="stock">국내 주식</option></select></label><label>분석 종목 <small>최대 5개 · 비워 두면 서버가 추천 종목에서 선택</small><input value={symbols} maxLength={150} onChange={event => setSymbols(event.target.value)} placeholder={market === 'upbit' ? 'KRW-BTC, KRW-ETH' : '005930, 000660'}/></label></div>
      {!!recommendations.length && <fieldset className="ai-symbol-picker"><legend>현재 추천 {marketName(market)}에서 선택</legend><div>{recommendations.map(item => {const selectedSymbol = selectedSymbols.includes(item.code); return <button type="button" key={item.code} className={selectedSymbol ? 'selected' : ''} aria-pressed={selectedSymbol} onClick={() => toggleSymbol(item.code)}><b>{item.name || item.code}</b><small>{item.code}</small></button>;})}</div><small>추천 목록은 종목 선택을 돕기 위한 것이며 AI 분석이나 수익을 보장하지 않습니다.</small></fieldset>}
      <label>어떤 내용을 비교할까요?<textarea rows="4" value={prompt} onChange={event => setPrompt(event.target.value)} minLength={1} maxLength={1500} required placeholder="예: 현재 설정과 손실 폭을 줄이는 후보를 비교해 주세요."/><small>{prompt.length} / 1,500자 · 이 입력란에 API 키나 개인정보를 넣지 마세요.</small></label>
      <div className="ai-form-grid ai-two"><label>편도 수수료 (bp)<input type="number" min="0" max="100" step="1" required value={feeBps} onChange={event => setFeeBps(event.target.value)}/></label><label>편도 체결 가격 차이 (bp)<input type="number" min="0" max="100" step="1" required value={slippageBps} onChange={event => setSlippageBps(event.target.value)}/></label></div>
      <p className="hint">1bp = 0.01%입니다. 매수·매도 양쪽에 각각 적용합니다. 수수료 기본값은 분석 가정이므로 본인 거래 조건에 맞게 확인해 주세요.</p>
      {market === 'upbit' && <label className="check ai-consent"><input type="checkbox" checked={includeAccount} onChange={event => setIncludeAccount(event.target.checked)}/><span><b>내 Upbit 계좌 요약을 DeepSeek에 전송하는 데 동의합니다</b><small>선택 사항입니다. 보유 종목·수량·평균 매수가 등의 요약이 외부 AI 서비스로 전달됩니다. API 비밀키는 전달하지 않습니다.</small></span></label>}
      <p className="hint">분석 요청을 보내면 입력한 질문, 현재 전략·설정·추천 종목과 조회한 시장 데이터가 DeepSeek로 전달됩니다. 민감한 내용을 입력하지 마세요.</p>
      <button className="primary" disabled={!config?.configured || Boolean(pending) || running || !prompt.trim()}>{pending === 'analysis' ? '대화 만드는 중…' : running ? '진행 중인 분석을 기다려 주세요' : !config?.configured ? '먼저 DeepSeek 키를 등록해 주세요' : '새 분석 대화 시작'}</button>
    </form></section>}

    <div className="ai-chat-workspace">
    <aside className="ai-conversation-list"><button className="primary ai-new-button" onClick={() => {detailRequests.current.cancel(); setSelectedId(null); setSelected(null); setProposal(null); setChatQuestion('');}}>＋ 새 대화</button><section className="ai-history"><div className="section-head ai-section-head"><h3>대화 <small>{count(history.total)}개</small></h3>{loading && <span className="ai-muted" role="status">불러오는 중…</span>}</div>{!history.items?.length ? <div className="empty"><b>아직 대화가 없습니다</b><span>새 분석 대화를 시작해 보세요.</span></div> : <div className="ai-history-list">{history.items.map(item => <button key={item.id} className={`ai-history-item ${String(item.id) === String(selectedId) ? 'selected' : ''}`} onClick={() => selectAnalysis(item.id)} aria-pressed={String(item.id) === String(selectedId)}><span><b>{marketName(item.market)} · {item.prompt || '분석 대화'}</b><time>{timestamp(item.created_at)}</time></span><span><b className={`ai-status ${String(item.status).toLowerCase()}`}>{AI_STATUS_LABELS[item.status] || item.status}</b><small>{count(item.usage_tokens)} 토큰</small></span></button>)}</div>}{pages > 1 && <nav className="pager" aria-label="AI 대화 목록 페이지"><button className="quiet" disabled={page === 0 || loading} onClick={() => setPage(value => value - 1)}>이전</button><span>{page + 1} / {pages}</span><button className="quiet" disabled={page + 1 >= pages || loading} onClick={() => setPage(value => value + 1)}>다음</button></nav>}</section></aside>
    <div className="ai-conversation-panel" ref={chatPanelRef}>

    {selectedId !== null && <section className={`ai-result ${showEvidence ? 'show-evidence' : ''}`} aria-label="선택한 분석 결과">
      <div className="section-head ai-section-head"><h3>{selected ? `${marketName(selected.market)} 분석 대화` : '대화 불러오는 중'}</h3><div className="ai-header-actions">{selected?.status === 'COMPLETED' && <button className="quiet compact" onClick={() => setShowEvidence(value => !value)}>{showEvidence ? '근거 접기' : '분석 근거'}</button>}{selected && !running && !chatRunning && !selected.applied_candidate_id && <button className="danger compact" disabled={pending === 'delete-chat'} onClick={deleteConversation}>{pending === 'delete-chat' ? '삭제 중…' : '삭제'}</button>}<button className="quiet compact" onClick={() => {detailRequests.current.cancel(); setSelectedId(null); setSelected(null); setProposal(null); setChatQuestion(''); setShowEvidence(false);}}>새 대화</button></div></div>
      {detailLoading && <div className="loading-row" role="status"><div className="loader"/>분석 결과를 확인하고 있습니다.</div>}
      {selected && <><p className="ai-muted">{timestamp(selected.created_at)} · {AI_STATUS_LABELS[selected.status] || selected.status} · {count(selected.usage_tokens)} 토큰{selected.include_account ? ' · 계좌 요약 포함' : ' · 계좌 요약 제외'}</p><article className="ai-chat-user ai-first-question"><b>나</b><p>{selected.prompt}</p></article>
        {running && <div className="info-note" role="status"><b>자료 조회 및 분석 중입니다.</b><span>3초마다 상태를 확인합니다. 화면을 닫아도 분석은 계속되며, 기록에서 다시 확인할 수 있습니다.</span></div>}
        {selected.status === 'FAILED' && <div className="error" role="alert"><b>분석을 완료하지 못했습니다.</b><p>{selected.error_message || '자료 또는 연결 상태를 확인한 뒤 새 분석을 요청해 주세요.'}</p><span>자동 재요청은 하지 않습니다. 새 분석은 별도 사용량이 발생할 수 있습니다.</span></div>}
        {selected.status === 'COMPLETED' && <>
          <AIReport report={result.report}/>
          <Notes title="주의 사항" items={result.warnings}/>
          <div className="info-note"><b>탐색 구간과 검증 구간을 나눠 비교했습니다.</b><span>탐색 구간으로 설정 후보를 살펴보고 뒤쪽 검증 구간에서 다시 계산합니다. 검증 거래가 없거나 분석 당시 설정이 변경된 결과는 적용할 수 없습니다. 표본이 작으면 비교 결과를 신뢰하기 어렵습니다.</span></div>
          <Dataset dataset={result.dataset}/>
          <div className="ai-candidates">{candidates.map(candidate => {
            const baseline = candidate.id === 'current' || candidate.id === 'baseline';
            const applied = String(selected.applied_candidate_id) === String(candidate.id);
            const eligible = candidateEligible(candidate);
            return <article className={`card ai-candidate ${applied ? 'applied' : ''}`} key={candidate.id}><div className="section-head ai-section-head"><h3>{candidate.label || '설정 후보'}</h3>{baseline && <span className="ai-mode">기존 설정</span>}{applied && <span className="ai-mode">적용 완료</span>}</div><dl className="ai-setting-list">{AI_SETTING_FIELDS.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{settingText(key, candidate.settings?.[key])}</dd></div>)}</dl><div className="ai-metric-grid"><Metrics title="탐색 구간" values={candidate.train}/><Metrics title="검증 구간" values={candidate.validation}/></div>{!eligible && !baseline && <p className="hint">검증이 충분하지 않아 적용할 수 없는 후보입니다.</p>}{master && !baseline && <button className="quiet" disabled={!eligible || Boolean(pending) || Boolean(selected.applied_candidate_id)} onClick={() => inspectCandidate(candidate)}>{applied ? '이 분석에서 이미 적용됨' : '현재 설정과 비교 후 적용'}</button>}</article>;
          })}</div>
          {!candidates.length && <div className="info-note">검증 가능한 설정 후보가 없습니다. 자료와 분석 설명을 확인해 주세요.</div>}
          {!master && <p className="hint">분석과 비교는 관리자도 볼 수 있지만, 실제 계산 설정 적용은 MASTER 권한만 가능합니다.</p>}
          {proposal && <section className="card ai-confirm" aria-label="계산 설정 적용 확인"><h3>실제 계산 설정을 변경할까요?</h3><p>{marketName(selected.market)} · {proposal.candidate.label || '선택한 후보'}</p><div className="ai-comparison"><div className="ai-comparison-heading"><b>항목</b><b>현재 설정</b><b>변경할 설정</b></div>{AI_SETTING_FIELDS.map(([key, label]) => <div key={key}><span>{label}</span><span>{settingText(key, proposal.current[key])}</span><strong>{settingText(key, proposal.candidate.settings?.[key])}</strong></div>)}</div><div className="info-note"><b>다음 계산부터 실제 운영에 영향을 줍니다.</b><span>자동매매가 켜져 있으면 이후 추천·매매 판단에 영향을 줄 수 있습니다. AI가 직접 주문하지는 않으며 자동매매의 켜짐/꺼짐 상태도 바꾸지 않습니다.</span></div>{stale && <div className="error" role="alert">분석 이후 현재 설정이 바뀌었습니다. 새 분석을 실행한 뒤 다시 비교해 주세요.</div>}<label className="check ai-consent"><input type="checkbox" checked={confirmed} disabled={stale || pending === 'apply'} onChange={event => setConfirmed(event.target.checked)}/><span>변경 전후 설정과 실제 자동매매에 미치는 영향을 확인했으며, 이 설정을 적용합니다.</span></label><div className="ai-actions"><button className="primary" disabled={!confirmed || stale || Boolean(pending)} onClick={applyCandidate}>{pending === 'apply' ? '설정 적용 중…' : '확인한 설정 적용'}</button><button className="quiet" disabled={pending === 'apply'} onClick={() => {setProposal(null); setConfirmed(false);}}>취소</button></div></section>}
          <Notes title="검증의 한계" items={result.limitations}/>
          <details className="ai-details"><summary>사용한 자료와 조회 기록</summary><Notes title="데이터 출처" items={result.data_sources}/>{Array.isArray(result.data_sources) && result.data_sources.filter(source => typeof source === 'object' && source !== null).map((source, index) => <p className="ai-source" key={index}>{source.name || source.source || source.provider || source.symbol || source.code || '시장 자료'}{(source.as_of || source.fetched_at || source.end_date) && <span> · {timestamp(source.as_of || source.fetched_at || source.end_date)}</span>}{source.start_date && <span> · 시작 {source.start_date}</span>}{source.bars != null && <span> · {count(source.bars)}개 봉</span>}</p>)}{Array.isArray(result.tool_calls) && result.tool_calls.map((call, index) => <p className="ai-source" key={index}>{typeof call === 'string' ? call : call?.name || call?.tool || '자료 조회'}{call?.status && <span> · {call.status}</span>}</p>)}{!result.data_sources?.length && !result.tool_calls?.length && <p className="hint">제공된 조회 기록이 없습니다.</p>}</details>
          <section className="ai-chat"><div className="ai-chat-thread">{conversations.map(message => <article key={message.id}><div className="ai-chat-user"><b>나</b><p>{message.question}</p></div><div className="ai-chat-assistant"><b>DeepSeek</b>{isAnalysisRunning(message.status) ? <p className="ai-muted">시세·뉴스·백테스트 자료를 확인하며 답변을 작성하고 있습니다…</p> : message.status === 'FAILED' ? <p className="error">{message.error_message || '답변을 완료하지 못했습니다.'}</p> : <><p className="ai-prose">{message.answer}</p>{message.research?.data_sources?.map((source, index) => <div className="ai-news-source" key={index}><b>{source.provider || source.source || source.code || '공개 자료'}</b>{source.query && <span>검색어: {source.query}</span>}{source.articles?.map((article, articleIndex) => <a key={articleIndex} href={article.link} target="_blank" rel="noreferrer">{article.title}<small>{article.source} · {timestamp(article.published_at)}</small></a>)}</div>)}<small className="ai-muted">{count(message.usage_tokens)} 토큰</small></>}</div></article>)}</div><form className="form ai-message-composer" onSubmit={askFollowUp}><label><span className="sr-only">메시지</span><textarea rows="3" minLength="1" maxLength="1500" required value={chatQuestion} onChange={event => setChatQuestion(event.target.value)} placeholder="메시지를 입력하세요. 필요한 경우 시세·RSS 뉴스·설정 백테스트를 조사합니다."/><small>{chatQuestion.length} / 1,500자 · Enter는 줄바꿈이며 버튼으로 전송합니다.</small></label><button className="primary" disabled={!chatQuestion.trim() || chatRunning || Boolean(pending)}>{pending === 'chat' ? '보내는 중…' : chatRunning ? '답변 작성 중…' : '보내기'}</button></form></section>
        </>}
      </>}
    </section>}
    {selectedId === null && <section className="ai-chat-empty"><b>새 분석 대화를 준비하고 있습니다.</b><span>위에서 시장과 종목을 고른 뒤 첫 메시지를 보내세요.</span></section>}
    </div></div>
  </div>;
}
