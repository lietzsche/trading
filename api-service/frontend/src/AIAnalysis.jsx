import React, {useCallback, useEffect, useRef, useState} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkCjkFriendly from 'remark-cjk-friendly/parseOnly';
import {api, createRequestGate} from './api';
import {AI_SETTING_FIELDS, AI_STATUS_LABELS, autoApplyEligible, candidateEligible, candidateRiskLabel, isAnalysisRunning, parseAnalysisSymbols, percentText, sameSettings, settingText, textItems} from './ai';
import './ai.css';
import {Icon, ResponsivePanel, Sheet, useMobile, useMobileChatLayout} from './MobileUI';
import {Toast} from './Feedback';

const API = '/admin/ai';
const count = value => Number(value || 0).toLocaleString('ko-KR');
const timestamp = value => value ? String(value).replace('T', ' ').slice(0, 16) : '—';
const analysisErrorText = value => String(value || '').includes('질문을 짧게 바꾸어')
  ? '이 기록은 간결 자동 재시도 기능이 적용되기 전에 AI 출력 길이가 초과되어 중단된 분석입니다.'
  : value || '자료 또는 연결 상태를 확인한 뒤 새 분석을 요청해 주세요.';
const marketName = value => value === 'upbit' ? 'Upbit' : '주식';
const defaults = {model: 'deepseek-flash'};
const automationDefaults = {enabled: false, trigger_mode: 'interval', interval_minutes: 60, auto_apply_settings: false};

export function Metrics({title, values}) {
  return <div className="ai-metrics"><h4>{title}</h4><dl>
    <div><dt>과거 수익률</dt><dd>{percentText(values?.return_pct)}</dd></div>
    <div><dt>최대 낙폭</dt><dd>{percentText(values?.max_drawdown_pct)}</dd></div>
    <div><dt>청산 완료 거래</dt><dd>{values?.trades == null ? '—' : `${count(values.trades)}회`}</dd></div>
  </dl>{values?.days != null && <small>비교한 일봉 {count(values.days)}개</small>}{(values?.start_date || values?.end_date) && <small>{values.start_date || '—'} ~ {values.end_date || '—'}</small>}</div>;
}

export function MarkdownAnswer({children}) {
  return <div className="ai-markdown"><ReactMarkdown remarkPlugins={[remarkGfm,remarkCjkFriendly]} skipHtml components={{
    a: ({children: label, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer">{label}</a>,
  }}>{typeof children === 'string' ? children : ''}</ReactMarkdown></div>;
}

export function AIReport({report}) {
  return <article className="ai-chat-assistant ai-first-answer"><b>DeepSeek</b><MarkdownAnswer>{typeof report === 'string' ? report : '분석 설명이 없습니다.'}</MarkdownAnswer></article>;
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

function PortfolioActions({items, onNavigate}) {
  if (!Array.isArray(items) || !items.length) return null;
  const labels = {SELL: '매도 검토', HOLD: '보유', WATCH: '판단 보류'};
  return <section className="ai-decision-section"><div className="section-head"><h3>종목별 결론</h3><small>AI 판단 · 최종 결정은 사용자</small></div><div className="ai-decision-grid">{items.map(item => <article className={`card ai-decision action-${String(item.action).toLowerCase()}`} key={item.code}><div className="section-head"><h3>{item.code}</h3><span className="ai-decision-label">{labels[item.action] || item.action}</span></div><p>{item.reason}</p>{Array.isArray(item.evidence)&&item.evidence.length>0&&<ul>{item.evidence.map((evidence,index)=><li key={index}>{evidence}</li>)}</ul>}<small>근거 확신도 {Number(item.confidence||0)}% · 성공 확률이 아닙니다</small>{item.action==='SELL'&&onNavigate&&<button className="danger compact" onClick={()=>onNavigate('account')}>내 계좌에서 수량 확인·매도</button>}</article>)}</div></section>;
}

function ValidationComparison({candidate, baseline}) {
  return <><div className="ai-comparison"><div className="ai-comparison-heading"><b>과거 검증</b><b>기존 설정</b><b>후보 설정</b></div>{[['return_pct', '수익률'], ['max_drawdown_pct', '최대 낙폭'], ['trades', '청산 횟수']].map(([key, label]) => <div key={key}><span>{label}</span><span>{key === 'trades' ? baseline?.validation?.[key] ?? '—' : percentText(baseline?.validation?.[key])}</span><strong>{key === 'trades' ? candidate?.validation?.[key] ?? '—' : percentText(candidate?.validation?.[key])}</strong></div>)}</div>{!autoApplyEligible(candidate, baseline) && <p className="info-note">이 후보는 자동 적용 기준(검증 20일·청산 3회·수익 개선·낙폭 악화 2%p 이내)을 통과하지 못했습니다. 수동 적용 전에 위험을 확인해 주세요.</p>}</>;
}

export function SettingRecommendation({candidates, baselineSettings, master, pending, onInspect}) {
  const baseline = (candidates || []).find(candidate => candidate.id === 'current' || candidate.id === 'baseline');
  const alternatives = (candidates || []).filter(candidate => candidate.id !== 'current' && candidate.id !== 'baseline');
  const eligible = alternatives.filter(candidate => autoApplyEligible(candidate, baseline)).sort((left, right) => Number(right.validation?.return_pct ?? -Infinity) - Number(left.validation?.return_pct ?? -Infinity));
  const recommended = eligible[0];

  if (!recommended) return (
    <section className="ai-setting-recommendation card">
      <div className="ai-setting-recommendation-head">
        <div>
          <span className="eyebrow">SETTING DECISION</span>
          <h3>현재 계산 설정 유지</h3>
          <p>검증 20일 이상·완료 거래 3회 이상·기존보다 높은 수익률·최대 낙폭 악화 2%p 이내를 모두 만족한 후보가 없습니다.</p>
        </div>
        <span className="ai-setting-verdict keep">유지 권장</span>
      </div>

      <div className="ai-setting-current">
        <b>유지할 계산 설정</b>
        <div className="ai-setting-table-wrap">
          <table className="ai-setting-comparison-table">
            <thead>
              <tr>
                <th>설정 항목</th>
                <th>현재 설정</th>
                <th>AI 판단</th>
                <th>결론</th>
              </tr>
            </thead>
            <tbody>
              {AI_SETTING_FIELDS.map(([key, label]) => (
                <tr key={key}>
                  <td className="col-label">{label}</td>
                  <td className="col-cur">{settingText(key, baselineSettings?.[key])}</td>
                  <td className="col-rec">유지</td>
                  <td className="col-status">
                    <span className="mini-badge badge-keep">유지</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <small>위 값이 이번 분석의 기준 설정입니다. 값이 ‘확인 불가’라면 오래된 분석 기록이므로 현재 설정을 다시 불러와 새 분석을 실행해 주세요.</small>
      <small>AI의 문장만으로 설정을 추천하지 않고 동일 데이터 백테스트를 통과한 값만 변경 후보로 표시합니다.</small>
    </section>
  );

  return (
    <section className="ai-setting-recommendation card">
      <div className="ai-setting-recommendation-head">
        <div>
          <span className="eyebrow">SETTING DECISION</span>
          <h3>{recommended.label || '검증된 설정 후보'}</h3>
          <p>AI가 제안한 값 중 과거 검증 조건을 통과했고, 검증 수익률이 가장 높은 후보입니다.</p>
        </div>
        <span className="ai-setting-verdict change">변경 검토</span>
      </div>

      <div className="ai-setting-table-wrap">
        <table className="ai-setting-comparison-table">
          <thead>
            <tr>
              <th>설정 항목</th>
              <th>현재 설정</th>
              <th>AI 추천</th>
              <th>결론</th>
            </tr>
          </thead>
          <tbody>
            {AI_SETTING_FIELDS.map(([key, label]) => {
              const curVal = settingText(key, baselineSettings?.[key]);
              const recVal = settingText(key, recommended.settings?.[key]);
              const isDiff = curVal !== recVal;
              return (
                <tr key={key} className={isDiff ? 'row-changed' : 'row-same'}>
                  <td className="col-label">{label}</td>
                  <td className="col-cur">{curVal}</td>
                  <td className={`col-rec ${isDiff ? 'highlight-rec' : ''}`}>{recVal}</td>
                  <td className="col-status">
                    <span className={`mini-badge ${isDiff ? 'badge-change' : 'badge-keep'}`}>
                      {isDiff ? '변경 검토' : '유지'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="ai-setting-score">
        <span>검증 수익률 <b>{percentText(recommended.validation?.return_pct)}</b></span>
        <span>최대 낙폭 <b>{percentText(recommended.validation?.max_drawdown_pct)}</b></span>
        <span>완료 거래 <b>{count(recommended.validation?.trades)}회</b></span>
      </div>

      {master && (
        <button className="primary compact" disabled={Boolean(pending)} onClick={() => onInspect(recommended)}>
          현재 설정과 비교하고 적용
        </button>
      )}
      <small>과거 검증 결과이며 미래 수익을 보장하지 않습니다. 적용 전 변경값을 다시 확인합니다.</small>
    </section>
  );
}

function ConfirmModal({ title, message, children, confirmText = '확인', cancelText = '취소', onConfirm, onClose }) {
  const cancelBtnRef = useRef(null);
  const modalRef = useRef(null);

  useEffect(() => {
    const prev = document.activeElement;
    cancelBtnRef.current?.focus();

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'Tab') {
        const focusable = modalRef.current?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!focusable?.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      prev?.focus();
    };
  }, [onClose]);

  return (
    <div className="safe-sell-overlay" onClick={onClose}>
      <div
        className="safe-sell-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        ref={modalRef}
        onClick={e => e.stopPropagation()}
      >
        <div className="safe-sell-header">
          <h3 id="confirm-dialog-title">{title}</h3>
          <button className="safe-sell-close-btn" aria-label="닫기" onClick={onClose}>✕</button>
        </div>
        <p style={{ margin: '14px 0 20px', color: 'var(--text-secondary)', lineHeight: 1.6, wordBreak: 'keep-all' }}>{message}</p>
        {children}
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button ref={cancelBtnRef} className="quiet" onClick={onClose}>{cancelText}</button>
          <button className="danger" onClick={async () => { await onConfirm(); onClose(); }}>{confirmText}</button>
        </div>
      </div>
    </div>
  );
}

export default function AIAnalysis({user, refreshToken = 0, setError, onNavigate, initialSymbol = '', settingsRequest=0, onSettingsConsumed}) {
  const mobile=useMobile();
  const pageRefElement=useRef(null),messageInputRef=useRef(null);
  const [disclaimerSheet,setDisclaimerSheet]=useState(false),[sharingSheet,setSharingSheet]=useState(false),[chatMenu,setChatMenu]=useState(false);
  const [listOpen,setListOpen]=useState(false),[settingsSection,setSettingsSection]=useState('connection');
  const [disclaimerOpen,setDisclaimerOpen]=useState(()=>{try{return localStorage.getItem('ai-disclaimer-closed')!=='true'}catch{return true}});
  const [coachClosed,setCoachClosed]=useState(()=>{try{return localStorage.getItem('ai-coach-closed')==='true'}catch{return false}});
  const [config, setConfig] = useState(null), [configDraft, setConfigDraft] = useState(defaults), [apiKey, setApiKey] = useState('');
  const [history, setHistory] = useState({items: [], total: 0, page: 0, page_size: 10}), [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState(null), [selected, setSelected] = useState(null), [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(true), [pending, setPending] = useState(''), [notice, setNotice] = useState(''), [localError, setLocalError] = useState('');
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [selectionMode, setSelectionMode] = useState(false), [checkedIds, setCheckedIds] = useState([]);
  const [automationOnly, setAutomationOnly] = useState(false);
  const automationOnlyRef = useRef(automationOnly);
  automationOnlyRef.current = automationOnly;
  const [market, setMarket] = useState('upbit'), [prompt, setPrompt] = useState('현재 전략과 설정을 점검하고, 과거 데이터로 비교한 설정 후보의 장단점과 위험을 설명해 주세요.');
  const [symbols, setSymbols] = useState(''), [includeAccount, setIncludeAccount] = useState(false), [feeBps, setFeeBps] = useState(5), [slippageBps, setSlippageBps] = useState(10);
  const [recommendations, setRecommendations] = useState([]), [chatQuestion, setChatQuestion] = useState(''), [includePortfolio, setIncludePortfolio] = useState(false);
  const [automation, setAutomation] = useState(null), [automationDraft, setAutomationDraft] = useState(automationDefaults);
  const [proposal, setProposal] = useState(null), [confirmed, setConfirmed] = useState(false), [detailVersion, setDetailVersion] = useState(0), [showEvidence, setShowEvidence] = useState(false);
  const [viewMode, setViewMode] = useState('summary'), [settingsOpen, setSettingsOpen] = useState(false);
  function openSettings(section='connection'){setSettingsSection(section);setSettingsOpen(true)}
  useEffect(()=>{if(settingsRequest){openSettings('connection');onSettingsConsumed?.()}},[settingsRequest,onSettingsConsumed]);
  const compactChat=mobile && viewMode==='chat';
  useMobileChatLayout(pageRefElement,compactChat);
  useEffect(()=>{const input=messageInputRef.current;if(input){input.style.height='auto';input.style.height=`${Math.max(44,Math.min(96,input.scrollHeight+2))}px`}},[chatQuestion,compactChat]);
  useEffect(()=>{
    if(!settingsOpen)return;
    const timer=setTimeout(()=>{const section=document.getElementById(`ai-settings-${settingsSection}`);if(section){section.open=true;section.scrollIntoView({block:'start'});}},50);
    return()=>clearTimeout(timer);
  },[settingsOpen,settingsSection]);
  const mounted = useRef(false), operation = useRef(false), pageRef = useRef(page), previousPage = useRef(page), errorHandler = useRef(setError), selectedIdRef = useRef(selectedId), chatBottomRef = useRef(null);
  const listRequests = useRef(createRequestGate()), detailRequests = useRef(createRequestGate());
  pageRef.current = page; errorHandler.current = setError; selectedIdRef.current = selectedId;

  useEffect(() => {
    if (initialSymbol) {
      setSelectedId(null);
      setSelected(null);
      setProposal(null);
      setDetailLoading(false);
      setIncludeAccount(false);
      selectedIdRef.current=null;
      setViewMode('chat');
      setMarket('upbit');
      setSymbols(initialSymbol);
      setPrompt(`${initialSymbol} 종목의 현재 수익률과 손절/목표가 도달 가능성, 시장 상황에 따른 대응 전략을 분석해 주세요.`);
    }
  }, [initialSymbol]);

  const showError = useCallback(error => {
    if (!mounted.current || error?.name === 'AbortError') return;
    if (error?.status === 401) {errorHandler.current?.(error); return;}
    setLocalError(error?.message || String(error));
  }, []);

  const refresh = useCallback(async (resetDraft = false, selectFirst = true) => {
    const request = listRequests.current.begin();
    setLoading(true);
    try {
      const [nextConfig, nextHistory, nextAutomation] = await Promise.all([
        api(`${API}/config`, {signal: request.signal}),
        api(`${API}/analyses?page=${pageRef.current}&automation_only=${automationOnlyRef.current}`, {signal: request.signal}),
        user.user_role === 'MASTER' ? api(`${API}/automation`, {signal: request.signal}) : Promise.resolve(null),
      ]);
      if (!request.isCurrent()) return;
      if (!nextHistory.items?.length && pageRef.current > 0) {
        pageRef.current -= 1;
        setPage(pageRef.current);
        return;
      }
      setConfig(nextConfig); setHistory(nextHistory);
      setCheckedIds(ids => ids.filter(id => nextHistory.items.some(item => item.id === id && !isAnalysisRunning(item.status) && !item.has_running_message)));
      if (nextAutomation) {
        setAutomation(nextAutomation);
        if (resetDraft) setAutomationDraft({enabled: Boolean(nextAutomation.enabled), trigger_mode: nextAutomation.trigger_mode || 'interval', interval_minutes: Number(nextAutomation.interval_minutes || 60), auto_apply_settings: Boolean(nextAutomation.auto_apply_settings)});
      }
      if (selectFirst && !initialSymbol && selectedIdRef.current === null && nextHistory.items?.length) setSelectedId(nextHistory.items[0].id);
      if (resetDraft) setConfigDraft({model: nextConfig.model || defaults.model});
    } catch (error) {if (request.isCurrent()) showError(error);}
    finally {if (request.isCurrent()) setLoading(false);}
  }, [showError, user.user_role, initialSymbol]);

  useEffect(() => {
    mounted.current = true;
    return () => {mounted.current = false; listRequests.current.cancel(); detailRequests.current.cancel();};
  }, []);

  useEffect(() => {refresh(true);}, [refresh, refreshToken]);
  useEffect(() => {if (previousPage.current !== page) {previousPage.current = page; refresh(false, false);}}, [refresh, page]);
  useEffect(() => {
    const controller = new AbortController();
    api(`${API}/recommendations/${market}`, {signal: controller.signal}).then(rows => {if (!controller.signal.aborted) setRecommendations(Array.isArray(rows) ? rows : []);}).catch(error => {if (error?.name !== 'AbortError') setRecommendations([]);});
    return () => controller.abort();
  }, [market, refreshToken]);

  useEffect(() => {
    if (selectedId === null) return;
    const request = detailRequests.current.begin();
    let timer;
    let inFlight = false;
    setDetailLoading(true);
    async function poll() {
      if (document.hidden || inFlight || !request.isCurrent()) return;
      inFlight = true;
      try {
        const result = await api(`${API}/analyses/${encodeURIComponent(selectedId)}`, {signal: request.signal});
        if (!request.isCurrent()) return;
        setSelected(result); setDetailLoading(false);
        if (isAnalysisRunning(result.status) || result.conversations?.some(item => isAnalysisRunning(item.status))) timer = setTimeout(poll, 3000);
        else refresh(false);
      } catch (error) {if (request.isCurrent()) {setDetailLoading(false); showError(error);}}
      finally {inFlight = false;}
    }
    function visibilityChanged() {clearTimeout(timer); if (!document.hidden) poll();}
    document.addEventListener('visibilitychange', visibilityChanged);
    poll();
    return () => {clearTimeout(timer); document.removeEventListener('visibilitychange', visibilityChanged); detailRequests.current.cancel();};
  }, [selectedId, detailVersion, refreshToken, refresh, showError]);

  async function runAction(name, action) {
    if (operation.current) return;
    operation.current = true; setPending(name); setNotice(''); setLocalError('');
    try {await action();} catch (error) {showError(error);}
    finally {operation.current = false; if (mounted.current) setPending('');}
  }

  function selectAnalysis(id) {
    if(mobile)setListOpen(false);
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

  async function saveAutomation(event) {
    event.preventDefault();
    await runAction('automation', async () => {
      const result = await api(`${API}/automation`, {method: 'PUT', body: JSON.stringify({...automationDraft, interval_minutes: Number(automationDraft.interval_minutes)})});
      if (!mounted.current) return;
      setAutomation(result); setAutomationDraft({enabled: Boolean(result.enabled), trigger_mode: result.trigger_mode, interval_minutes: Number(result.interval_minutes), auto_apply_settings: Boolean(result.auto_apply_settings)});
      setNotice(result.enabled ? 'AI 정기 판단을 켰습니다. AI가 주문을 직접 내리지는 않습니다.' : 'AI 정기 판단을 껐습니다.');
    });
  }

  async function runAutomationNow() {
    await runAction('automation-run', async () => {
      const result = await api(`${API}/automation/run`, {method: 'POST'});
      if (!mounted.current) return;
      setPage(0); selectAnalysis(result.id); setNotice('AI 판단을 시작했습니다. 완료 후 이 대화에서 결과를 확인할 수 있습니다.'); await refresh(false);
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
      await api(`${API}/analyses/${encodeURIComponent(selectedId)}/messages`, {method: 'POST', body: JSON.stringify({question, include_portfolio: includePortfolio})});
      if (!mounted.current) return;
      setChatQuestion(''); setIncludePortfolio(false); setNotice('메시지를 보냈습니다. 필요한 경우 종목·시세·기술 통계·뉴스·백테스트 자료를 조회합니다.');
      setDetailVersion(value => value + 1); await refresh(false);
    });
  }

  async function deleteTargetConversation(itemOrId) {
    const targetId = typeof itemOrId === 'object' && itemOrId !== null ? itemOrId.id : itemOrId;
    if (targetId == null) return;
    const targetItem = typeof itemOrId === 'object' && itemOrId !== null
      ? itemOrId
      : (history.items || []).find(it => String(it.id) === String(targetId)) || selected;

    if (targetItem?.has_running_message || targetItem?.conversations?.some(message => isAnalysisRunning(message.status))) {
      setLocalError('후속 답변이 진행 중인 대화는 완료 후 삭제할 수 있습니다.');
      return;
    }
    if (targetItem?.status === 'RUNNING' || targetItem?.status === 'PENDING') {
      setLocalError('현재 분석이 진행 중인 대화는 완료 전까지 삭제할 수 없습니다.');
      return;
    }

    setConfirmDialog({
      title: targetItem?.applied_candidate_id ? '감사 기록 숨기기' : 'AI 대화 삭제',
      message: targetItem?.applied_candidate_id
        ? '설정을 적용한 기록은 안전 감사를 위해 서버에 보존됩니다. 내 대화 목록에서 숨길까요?'
        : '이 AI 대화와 모든 메시지를 삭제할까요? 복구할 수 없습니다.',
      onConfirm: async () => {
        await runAction(`delete-chat-${targetId}`, async () => {
          await api(`${API}/analyses/${encodeURIComponent(targetId)}`, {method: 'DELETE'});
          if (!mounted.current) return;
          if (String(selectedId) === String(targetId)) {
            detailRequests.current.cancel();
            selectedIdRef.current = null;
            setSelectedId(null);
            setSelected(null);
            setProposal(null);
            setShowEvidence(false);
          }
          setNotice(targetItem?.applied_candidate_id ? '감사 기록을 대화 목록에서 숨겼습니다.' : 'AI 대화를 삭제했습니다.');
          await refresh(false, false);
        });
      }
    });
  }

  function deleteConversation() {
    deleteTargetConversation(selected);
  }

  function deleteCheckedConversations() {
    const ids = [...checkedIds];
    setConfirmDialog({title: '선택한 대화 정리', message: `${ids.length}개 대화를 정리할까요? 설정 적용 기록은 숨기고 보존하며, 나머지는 메시지와 함께 삭제합니다. 진행 중인 대화는 건너뜁니다.`, onConfirm: async () => {
      await runAction('bulk-delete', async () => {
        const result = await api(`${API}/analyses/bulk-delete`, {method: 'POST', body: JSON.stringify({ids})});
        if (!mounted.current) return;
        if (ids.includes(selectedIdRef.current) && !result.skipped.some(item => item.id === selectedIdRef.current)) {
          detailRequests.current.cancel(); selectedIdRef.current = null;
          setSelectedId(null); setSelected(null); setProposal(null); setShowEvidence(false);
        }
        setCheckedIds([]); setSelectionMode(false);
        setNotice(`삭제 ${result.deleted} · 숨김 ${result.hidden} · 건너뜀 ${result.skipped.length}`);
        await refresh(false, false);
      });
    }});
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

  function confirmRevert() {
    const analysis = selected;
    setConfirmDialog({title: '적용 전 설정으로 되돌리기', confirmText: '되돌리기', message: '아래 설정으로 복원합니다. 적용 이후 설정이 바뀌었다면 복원은 차단됩니다.',
      content: <dl className="ai-dataset">{AI_SETTING_FIELDS.map(([key,label]) => <div key={key}><dt>{label}</dt><dd>{settingText(key, analysis.settings_snapshot?.[key])}</dd></div>)}</dl>,
      onConfirm: async () => {await runAction('revert', async () => {
        await api(`${API}/analyses/${analysis.id}/revert`, {method: 'POST'});
        if (!mounted.current) return;
        setProposal(null); setNotice('적용 전 설정으로 되돌렸습니다. 다음 계산부터 반영됩니다.'); setDetailVersion(value => value + 1);
      });}});
  }

  const conversations = Array.isArray(selected?.conversations) ? selected.conversations : [];
  const chatRunning = conversations.some(item => isAnalysisRunning(item.status));
  const running = isAnalysisRunning(selected?.status), used = config?.usage_today || {};
  const pages = Math.max(1, Math.ceil(history.total / (history.page_size || 10)));
  const result = selected?.result || {}, candidates = Array.isArray(result.candidates) ? result.candidates : [];
  const baselineSettings = candidates.find(item => item.id === 'current' || item.id === 'baseline')?.settings;
  const selectedSymbols = (() => {try {return parseAnalysisSymbols(symbols, market);} catch {return [];}})();
  const master = user.user_role === 'MASTER';
  const stale = Boolean(proposal && !sameSettings(proposal.current, selected?.settings_snapshot));

  useEffect(() => {
    if (!selected || !chatBottomRef.current) return;
    const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if(mobile){const frame=requestAnimationFrame(()=>{const thread=chatBottomRef.current?.closest('.ai-chat-thread');if(thread)thread.scrollTop=thread.scrollHeight;});return()=>cancelAnimationFrame(frame);}
    chatBottomRef.current.scrollIntoView({behavior: (!reducedMotion && conversations.length) ? 'smooth' : 'auto', block: 'end'});
  }, [selectedId, selected?.status, conversations.length, conversations.at(-1)?.status, viewMode, mobile]);

  const decisions = Array.isArray(result.portfolio_actions) ? result.portfolio_actions : [];
  const decisionCounts = decisions.reduce((values,item) => ({...values,[item.action]:(values[item.action]||0)+1}), {});

  return <div className="ai-page" data-mode={viewMode} ref={pageRefElement}>
    {!compactChat && !loading && !config?.configured && !coachClosed && <section className="card ai-coach"><div className="section-head"><h3>여기서 할 수 있는 일</h3><button className="quiet" onClick={()=>{setCoachClosed(true);try{localStorage.setItem('ai-coach-closed','true')}catch{}}}>닫기</button></div><button className="quiet" onClick={()=>openSettings('connection')}>1. DeepSeek 키 등록</button><button className="quiet" onClick={()=>{setSelectedId(null);setSelected(null);setViewMode('chat')}}>2. 첫 분석 시작</button>{master&&<button className="quiet" onClick={()=>openSettings('automation')}>3. 정기 판단 설정</button>}</section>}
    <section className="ai-cockpit"><div><span className="eyebrow">AI INVESTMENT DESK</span><h2>투자 판단</h2><p>{selected?.status === 'COMPLETED' ? `${timestamp(selected.completed_at || selected.created_at)} 분석 기준` : '계좌·추천·설정·과거 가격을 한곳에서 검토합니다.'}</p></div><div className="ai-cockpit-stats"><span><small>매도 검토</small><b className="sell">{decisionCounts.SELL || 0}</b></span><span><small>보유</small><b className="hold">{decisionCounts.HOLD || 0}</b></span><span><small>판단 보류</small><b className="watch">{decisionCounts.WATCH || 0}</b></span></div><button className="quiet ai-settings-button" onClick={()=>openSettings()}><Icon name="settings"/><span>AI 설정</span></button><div className="ai-state-chips"><button onClick={()=>openSettings('connection')}>{config?.configured?'키 등록됨':'키 등록 필요'}</button>{master&&<><button onClick={()=>openSettings('automation')}>{automation?.enabled?`정기 판단 켜짐 · ${automation.interval_minutes%60===0?`${automation.interval_minutes/60}시간`:`${automation.interval_minutes}분`}마다`:'정기 판단 꺼짐'}</button><button className={automation?.auto_apply_settings?'warning':''} onClick={()=>openSettings('automation')}>{automation?.auto_apply_settings?'자동 적용 켜짐':'자동 적용 꺼짐'}</button></>}</div></section>
    <nav className="ai-view-tabs" aria-label="AI 화면"><button className={viewMode==='summary'?'active':''} onClick={()=>setViewMode('summary')}>판단 요약</button><button className={viewMode==='chat'?'active':''} onClick={()=>setViewMode('chat')}>AI 대화</button><button className={viewMode==='evidence'?'active':''} onClick={()=>setViewMode('evidence')}>근거·설정</button></nav>
    {localError && <div className="error" role="alert">{localError}<button className="quiet compact" onClick={() => {setLocalError(''); refresh(false); setDetailVersion(value => value + 1);}}>다시 조회</button></div>}
    <Toast message={notice} onClose={()=>setNotice('')}/>
    {viewMode === 'summary' && <button className="quiet compact" disabled={Boolean(pending) || loading} onClick={() => {setViewMode('chat'); setListOpen(true); setSelectionMode(true); setCheckedIds([]);}}>대화 선택</button>}
    {!compactChat && <details className="ai-disclaimer" open={disclaimerOpen} onToggle={event=>{const open=event.currentTarget.open;setDisclaimerOpen(open);try{localStorage.setItem('ai-disclaimer-closed',String(!open))}catch{}}}><summary>과거 데이터 검증 안내 · 자세히</summary><div className="info-note"><b>수익 예측이 아닌 과거 데이터 검증입니다.</b><span>종목별 독립·동일 비중으로 계산하는 단순 시뮬레이션이며 실제 자동매매 전체를 재현하지 않습니다. 수수료와 가격 차이를 반영해도 미체결·유동성·미래 시장 변동은 보장할 수 없습니다. 실제 수익을 약속하지 않습니다.</span></div></details>}
    {compactChat && <div className="ai-chat-toolbar">
      <button className="quiet ai-chat-list-button" aria-expanded={listOpen} onClick={()=>setListOpen(true)}>대화 {count(history.total)}개 ▾</button>
      <button className="quiet" aria-label="투자 위험 안내" onClick={()=>setDisclaimerSheet(true)}><Icon name="info"/></button>
      <button className="quiet ai-chat-settings" aria-label="AI 설정" onClick={()=>openSettings()}><Icon name="settings"/>{automation?.auto_apply_settings&&<span className="ai-warning-dot" aria-label="자동 적용 켜짐"/>}</button>
      <button className="quiet" aria-label="대화 메뉴" onClick={()=>setChatMenu(true)}><Icon name="ellipsis"/></button>
    </div>}
    {disclaimerSheet && <Sheet title="투자 위험 안내" onClose={()=>setDisclaimerSheet(false)}><div className="info-note"><b>수익 예측이 아닌 과거 데이터 검증입니다.</b><span>종목별 독립·동일 비중으로 계산하는 단순 시뮬레이션이며 실제 자동매매 전체를 재현하지 않습니다. 수수료와 가격 차이를 반영해도 미체결·유동성·미래 시장 변동은 보장할 수 없습니다. 실제 수익을 약속하지 않습니다.</span></div></Sheet>}
    {sharingSheet && <Sheet title="무엇이 전송되나요?" onClose={()=>setSharingSheet(false)}><p>이번 질문에 현재 계좌와 최근 주문 100건 요약 포함</p><p>Upbit 잔고·수량·평균 매수가와 주문 상태가 DeepSeek에 전달됩니다. API 키와 주문 번호는 제외됩니다.</p></Sheet>}
    {chatMenu && <Sheet title="대화 메뉴" onClose={()=>setChatMenu(false)}><div className="mobile-sheet-group-items">
      {selected && !running && !chatRunning && <button className="danger" disabled={Boolean(pending)} onClick={()=>{setChatMenu(false);deleteTargetConversation(selected)}}>{selected.applied_candidate_id?'목록에서 숨기기':'대화 삭제'}</button>}
      <button className="quiet" onClick={()=>{setChatMenu(false);detailRequests.current.cancel();setSelectedId(null);setSelected(null);setProposal(null);setChatQuestion('');setShowEvidence(false)}}>새 분석</button>
      {master && selected?.applied_candidate_id && !selected.reverted_at && <button className="quiet" disabled={Boolean(pending)} onClick={()=>{setChatMenu(false);confirmRevert()}}>적용 전 설정으로 되돌리기</button>}
    </div></Sheet>}

    {settingsOpen && <ResponsivePanel mobile={mobile} title="AI 설정" onClose={()=>setSettingsOpen(false)} className="ai-settings-panel"><details className="card ai-config" id="ai-settings-connection" open={!config?.configured || undefined}>
      <summary><span>DeepSeek 연결 설정</span><span className={`status-pill ${config?.configured ? 'on' : 'off'}`}>{config?.configured ? '키 등록됨' : '키 등록 필요'}</span></summary>
      <form className="form" onSubmit={saveConfig}>
        <p className="hint">내 계정의 키와 분석 기록만 사용합니다. 키는 서버에 암호화해 저장하며 다시 표시하지 않습니다. Upbit 비밀키·로그인 비밀번호는 AI에 보내지 않습니다.</p>
        <label>DeepSeek API 키<input type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} autoComplete="new-password" maxLength={255} placeholder={config?.configured ? '변경할 때만 새 키 입력' : 'DeepSeek API 키 입력'} required={!config?.configured}/>{config?.key_hint && <small>등록된 키: {config.key_hint}</small>}</label>
        <div className="ai-form-grid ai-one"><label>분석 모델<select value={configDraft.model} onChange={event => setConfigDraft({...configDraft, model: event.target.value})}><option value="deepseek-flash">DeepSeek Flash</option>{configDraft.model !== 'deepseek-flash' && <option value={configDraft.model}>{configDraft.model}</option>}</select></label></div>
        <div className="ai-actions"><button className="primary" disabled={Boolean(pending) || loading}>{pending === 'config' ? '저장 중…' : '연결 설정 저장'}</button><button type="button" className="quiet" disabled={!config?.configured || Boolean(pending)} onClick={() => runAction('test', async () => {await api(`${API}/config/test`, {method: 'POST'}); if (mounted.current) setNotice('저장된 API 키로 연결을 확인했습니다. 분석 요청은 실행하지 않았습니다.');})}>{pending === 'test' ? '확인 중…' : '저장된 키 연결 확인'}</button><button type="button" className="danger" disabled={!config?.configured || Boolean(pending)} onClick={() => {setConfirmDialog({title: 'DeepSeek API 키 삭제', message: '저장된 DeepSeek API 키를 삭제할까요? 새 분석에는 키를 다시 등록해야 합니다.', onConfirm: async () => {await runAction('delete', async () => {await api(`${API}/config`, {method: 'DELETE'}); if (mounted.current) {setApiKey(''); setNotice('DeepSeek API 키를 삭제했습니다.'); await refresh(true);}});}});}}>키 삭제</button></div>
      </form>
    </details>

    <section className="ai-usage" aria-label="오늘의 AI 사용량"><span>오늘 AI 요청 <b>{count(used.runs)}회</b></span><span>오늘 사용량 <b>{count(used.tokens)} 토큰</b></span><span>한 답변의 자료 조회 <b>최대 {config?.max_tool_calls || 4}회</b></span><small>앱 자체의 일일 대화 제한은 없습니다. DeepSeek 계정의 잔액·속도·사용 한도를 따르며, 각 요청은 안전을 위해 최대 실행 시간과 출력 길이만 제한합니다.</small></section>

    {master && <details className="card ai-config" id="ai-settings-automation"><summary><span>AI 정기 판단</span><span className={`status-pill ${automation?.enabled ? 'on' : 'off'}`}>{automation?.enabled ? '사용 중' : '꺼짐'}</span></summary><form className="form" onSubmit={saveAutomation}>
      <div className="info-note"><b>AI는 주문을 직접 내리지 않습니다.</b><span>보유 종목의 매도·보유 판단과 계산 설정 후보를 만들며, 설정 자동 적용을 켜더라도 충분한 검증을 통과한 후보만 반영합니다. 실제 주문은 기존 자동매매 규칙 또는 사용자의 직접 확인으로만 실행됩니다.</span></div>
      <label className="check ai-consent"><input type="checkbox" checked={automationDraft.enabled} onChange={event => setAutomationDraft({...automationDraft, enabled: event.target.checked})}/><span><b>정기적으로 계좌·추천·설정·과거 가격을 분석</b><small>Upbit 계좌 요약이 DeepSeek에 전송됩니다. DeepSeek 키와 Upbit API 키 원문은 전송하지 않습니다.</small></span></label>
      <div className="ai-form-grid ai-two"><label>실행 조건<select value={automationDraft.trigger_mode} onChange={event => setAutomationDraft({...automationDraft, trigger_mode: event.target.value})}><option value="interval">정해진 시간마다</option><option value="recommendation_change">추천 또는 설정이 바뀔 때</option></select></label><label>최소 실행 간격<input type="number" min="60" max="1440" step="10" value={automationDraft.interval_minutes} onChange={event => setAutomationDraft({...automationDraft, interval_minutes: event.target.value})}/><small>60~1,440분</small></label></div>
      <label className="check ai-consent"><input type="checkbox" checked={automationDraft.auto_apply_settings} onChange={event => setAutomationDraft({...automationDraft, auto_apply_settings: event.target.checked})}/><span><b>검증을 통과한 계산 설정만 자동 적용</b><small>검증 20일 이상·청산 3회 이상, 기존보다 수익률이 높고 최대 낙폭이 2%p 넘게 악화되지 않은 후보만 적용합니다. 자동매매 상태와 주문은 변경하지 않습니다.</small></span></label>
      <p className="hint">최근 실행 {timestamp(automation?.last_started_at)} · 다음 확인 {automation?.enabled ? timestamp(automation?.next_run_at) : '꺼짐'}{automation?.last_error ? ` · 최근 오류: ${automation.last_error}` : ''}</p>
      <div className="ai-actions"><button className="primary" disabled={Boolean(pending) || !config?.configured}>{pending === 'automation' ? '저장 중…' : '자동 판단 설정 저장'}</button><button type="button" className="quiet" disabled={Boolean(pending) || !config?.configured} onClick={runAutomationNow}>{pending === 'automation-run' ? '시작 중…' : '지금 한 번 판단'}</button></div>
    </form></details>}</ResponsivePanel>}

    {selectedId === null && <section className="card ai-new-chat"><div className="section-head ai-section-head"><h3>새 분석 대화</h3><span className="ai-muted">첫 메시지와 함께 백테스트를 시작합니다</span></div><form className="form" onSubmit={startAnalysis}>
      <div className="ai-form-grid ai-two"><label>시장<select value={market} onChange={event => {setMarket(event.target.value); setSymbols(''); setIncludeAccount(false); setFeeBps(event.target.value === 'upbit' ? 5 : 15);}}><option value="upbit">Upbit · 원화 마켓</option><option value="stock">주식 · 국내/미국</option></select></label><label>분석 종목 <small>최대 5개 · 비워 두면 서버가 추천 종목에서 선택</small><input value={symbols} maxLength={150} onChange={event => setSymbols(event.target.value)} placeholder={market === 'upbit' ? 'KRW-BTC, KRW-ETH' : '005930, US:AAPL'}/></label></div>
      {!!recommendations.length && <fieldset className="ai-symbol-picker"><legend>현재 추천 {marketName(market)}에서 선택</legend><div>{recommendations.map(item => {const selectedSymbol = selectedSymbols.includes(item.code); return <button type="button" key={item.code} className={selectedSymbol ? 'selected' : ''} aria-pressed={selectedSymbol} onClick={() => toggleSymbol(item.code)}><b>{item.name || item.code}</b><small>{item.code}</small></button>;})}</div><small>추천 목록은 종목 선택을 돕기 위한 것이며 AI 분석이나 수익을 보장하지 않습니다.</small></fieldset>}
      <label>어떤 내용을 비교할까요?<textarea rows="4" value={prompt} onChange={event => setPrompt(event.target.value)} minLength={1} maxLength={1500} required placeholder="예: 현재 설정과 손실 폭을 줄이는 후보를 비교해 주세요."/><small>{prompt.length} / 1,500자 · 이 입력란에 API 키나 개인정보를 넣지 마세요.</small></label>
      <div className="ai-form-grid ai-two"><label>편도 수수료 (bp)<input type="number" min="0" max="100" step="1" required value={feeBps} onChange={event => setFeeBps(event.target.value)}/></label><label>편도 체결 가격 차이 (bp)<input type="number" min="0" max="100" step="1" required value={slippageBps} onChange={event => setSlippageBps(event.target.value)}/></label></div>
      <p className="hint">1bp = 0.01%입니다. 매수·매도 양쪽에 각각 적용합니다. 수수료 기본값은 분석 가정이므로 본인 거래 조건에 맞게 확인해 주세요.</p>
      {market === 'upbit' && <label className="check ai-consent"><input type="checkbox" checked={includeAccount} onChange={event => setIncludeAccount(event.target.checked)}/><span><b>내 Upbit 계좌 요약을 DeepSeek에 전송하는 데 동의합니다</b><small>선택 사항입니다. 보유 종목·수량·평균 매수가 등의 요약이 외부 AI 서비스로 전달됩니다. API 비밀키는 전달하지 않습니다.</small></span></label>}
      <p className="hint">분석 요청을 보내면 입력한 질문, 현재 전략·설정·추천 종목과 조회한 시장 데이터가 DeepSeek로 전달됩니다. 민감한 내용을 입력하지 마세요.</p>
      <button className="primary" disabled={!config?.configured || Boolean(pending) || running || !prompt.trim()}>{pending === 'analysis' ? '대화 만드는 중…' : running ? '진행 중인 분석을 기다려 주세요' : !config?.configured ? '먼저 DeepSeek 키를 등록해 주세요' : '새 분석 대화 시작'}</button>
    </form></section>}

    {mobile && viewMode === 'evidence' && <button className="quiet ai-list-trigger" aria-expanded={listOpen} onClick={()=>setListOpen(true)}>대화 {count(history.total)}개 <span>▾</span></button>}
    <div className={`ai-chat-workspace ${selectionMode ? 'ai-selection-mode' : ''}`} data-view={viewMode}>
    <ResponsivePanel mobile={mobile} open={!mobile || listOpen} title="AI 대화 목록" onClose={()=>{setListOpen(false);setSelectionMode(false);setCheckedIds([])}} className="ai-list-sheet">
    {viewMode !== 'summary' && <button className="quiet ai-history-filter" aria-pressed={automationOnly} disabled={Boolean(pending) || loading} onClick={() => {pageRef.current = 0; previousPage.current = 0; setPage(0); setCheckedIds([]); automationOnlyRef.current = !automationOnlyRef.current; setAutomationOnly(automationOnlyRef.current); refresh(false, false);}}>자동 판단만 보기 {automationOnly ? '✓' : ''}</button>}
    <aside className={`ai-conversation-list ${selectionMode ? 'ai-selecting' : ''}`}><button className="primary ai-new-button" onClick={() => {detailRequests.current.cancel(); setSelectedId(null); setSelected(null); setProposal(null); setChatQuestion('');}}>＋ 새 대화</button><section className="ai-history"><div className="section-head ai-section-head"><h3>대화 <small>{count(history.total)}개</small></h3><button className="quiet compact" disabled={Boolean(pending)} onClick={() => {if (!selectionMode && viewMode === 'summary') setViewMode('chat'); setSelectionMode(value => !value); setCheckedIds([]);}}>{selectionMode ? '선택 취소' : '선택'}</button>{loading && <span className="ai-muted" role="status">불러오는 중…</span>}</div>{selectionMode && <button className="quiet ai-select-all" disabled={loading || Boolean(pending)} onClick={() => setCheckedIds(history.items.filter(item => !isAnalysisRunning(item.status) && !item.has_running_message).map(item => item.id))}>이 페이지 전체 선택</button>}{!history.items?.length ? <div className="empty"><b>아직 대화가 없습니다</b><span>새 분석 대화를 시작해 보세요.</span><button type="button" className="empty-action-btn" onClick={() => {detailRequests.current.cancel(); setSelectedId(null); setSelected(null); setProposal(null); setChatQuestion('');}}>새 대화 시작하기</button></div> : <div className="ai-history-list">{history.items.map(item => {
      const isSelected = String(item.id) === String(selectedId);
      const isApplied = Boolean(item.applied_candidate_id);
      const isRunning = item.status === 'RUNNING' || item.status === 'PENDING' || item.has_running_message;
      const isDeleting = pending === `delete-chat-${item.id}`;
      return (
        <div key={item.id} className={`ai-history-item-row ${isSelected ? 'selected' : ''}`}>
          {selectionMode && <label className="ai-history-check"><input type="checkbox" aria-label={`${item.prompt || '대화'} 선택`} disabled={isRunning || Boolean(pending)} checked={checkedIds.includes(item.id)} onChange={event => setCheckedIds(ids => event.target.checked ? [...ids, item.id] : ids.filter(id => id !== item.id))}/></label>}
          <button type="button" className="ai-history-item-btn" disabled={selectionMode && (isRunning || Boolean(pending))} onClick={() => selectionMode ? setCheckedIds(ids => ids.includes(item.id) ? ids.filter(id => id !== item.id) : [...ids, item.id]) : selectAnalysis(item.id)} aria-pressed={selectionMode ? checkedIds.includes(item.id) : isSelected}>
            <div className="ai-history-item-info">
              <b>{marketName(item.market)} · {item.prompt || '분석 대화'}{item.automation_run ? ' · 자동 판단' : ''}</b>
              <time>{timestamp(item.created_at)}</time>
            </div>
            <div className="ai-history-item-meta">
              <b className={`ai-status ${String(item.status).toLowerCase()}`}>{AI_STATUS_LABELS[item.status] || item.status}</b>
              {isApplied && <span className="ai-applied-tag" title="실제 설정 적용 기록 (감사 보존)">적용 보존</span>}
              <small>{count(item.usage_tokens)} 토큰</small>
            </div>
          </button>
          {!selectionMode && <button
            type="button"
            className="ai-item-delete-btn"
            title={isApplied ? '감사 기록은 보존하고 목록에서 숨기기' : isRunning ? '진행 중인 분석은 삭제할 수 없습니다' : '대화 삭제'}
            disabled={Boolean(pending) || isRunning}
            onClick={(e) => {
              e.stopPropagation();
              deleteTargetConversation(item);
            }}
            aria-label={`${item.prompt || '대화'} 삭제`}
          >
            {isDeleting ? '…' : isApplied ? '숨김' : '✕'}
          </button>}
        </div>
      );
    })}</div>}{pages > 1 && <nav className="pager" aria-label="AI 대화 목록 페이지"><button className="quiet" disabled={page === 0 || loading} onClick={() => setPage(value => value - 1)}>이전</button><span>{page + 1} / {pages}</span><button className="quiet" disabled={page + 1 >= pages || loading} onClick={() => setPage(value => value + 1)}>다음</button></nav>}</section></aside>
    {selectionMode && <div className="ai-bulk-bar" role="region" aria-label="선택한 대화 정리"><span>{checkedIds.length}개 선택</span><button className="danger" disabled={!checkedIds.length || Boolean(pending) || loading} onClick={deleteCheckedConversations}>{pending === 'bulk-delete' ? '처리 중…' : (() => {const hidden = history.items.filter(item => checkedIds.includes(item.id) && item.applied_candidate_id).length; return hidden ? `${checkedIds.length - hidden}개 삭제 · ${hidden}개 숨김` : `${checkedIds.length}개 삭제`;})()}</button></div>}
    </ResponsivePanel>
    <div className="ai-conversation-panel">

    {selectedId !== null && <section className={`ai-result ${(showEvidence || viewMode === 'evidence') ? 'show-evidence' : ''}`} aria-label="선택한 분석 결과">
      <div className="section-head ai-section-head">
        <h3>{selected ? `${marketName(selected.market)} 분석` : '분석 불러오는 중'}</h3>
        <div className="ai-header-actions">
          {master && selected?.applied_candidate_id && !selected.reverted_at && <button className="quiet compact" disabled={Boolean(pending)} onClick={confirmRevert}>적용 전 설정으로 되돌리기</button>}
          {selected?.reverted_at && <span className="hint">적용 전 설정 복원 완료 · {timestamp(selected.reverted_at)}</span>}
          {selected && !running && !chatRunning && <button
            type="button"
            className={selected.applied_candidate_id ? 'quiet compact' : 'danger compact'}
            disabled={Boolean(pending?.startsWith('delete-chat'))}
            onClick={() => deleteTargetConversation(selected)}
            title={selected.applied_candidate_id ? '설정 적용 이력은 보존하고 목록에서만 숨깁니다.' : '대화와 후속 메시지를 삭제합니다.'}
          >
            {pending?.startsWith('delete-chat') ? '처리 중…' : selected.applied_candidate_id ? '목록에서 숨기기' : '대화 삭제'}
          </button>}
          <button className="quiet compact" onClick={() => {detailRequests.current.cancel(); setSelectedId(null); setSelected(null); setProposal(null); setChatQuestion(''); setShowEvidence(false); setViewMode('chat');}}>새 분석</button>
        </div>
      </div>
      {detailLoading && <div className="loading-row" role="status"><div className="loader"/>분석 결과를 확인하고 있습니다.</div>}
      {selected && <><p className="ai-muted">{timestamp(selected.created_at)} · {AI_STATUS_LABELS[selected.status] || selected.status} · {count(selected.usage_tokens)} 토큰{selected.include_account ? ' · 계좌 요약 포함' : ' · 계좌 요약 제외'}{selected.automation_run ? ' · AI 자동 판단' : ''}</p>{selected.automation_note && <div className="info-note"><b>자동 판단 처리 결과</b><span>{selected.automation_note}</span></div>}<article className="ai-chat-user ai-first-question"><b>{selected.automation_run ? '자동 판단 요청' : '나'}</b><p>{selected.prompt}</p></article>
        {running && <div className="info-note" role="status"><b>자료 조회 및 분석 중입니다.</b><span>3초마다 상태를 확인합니다. 화면을 닫아도 분석은 계속되며, 기록에서 다시 확인할 수 있습니다.</span></div>}
        {selected.status === 'FAILED' && <div className="error" role="alert"><b>분석을 완료하지 못했습니다.</b><p>{analysisErrorText(selected.error_message)}</p><span>현재는 출력 길이 초과 시 서버가 한 번 간결하게 자동 재요청합니다. 이 기록은 재요청까지 실패했거나 다른 오류가 발생한 경우입니다.</span></div>}
        {selected.status === 'COMPLETED' && <>
          <AIReport report={result.report}/>
          <PortfolioActions items={result.portfolio_actions} onNavigate={onNavigate}/>
          <SettingRecommendation candidates={candidates} baselineSettings={baselineSettings} master={master} pending={pending} onInspect={inspectCandidate}/>
          <details className="ai-evidence-section"><summary>주의 사항</summary><Notes title="주의 사항" items={result.warnings}/></details>
          <details className="ai-evidence-section"><summary>검증 조건</summary><div className="info-note"><b>탐색 구간과 검증 구간을 나눠 비교했습니다.</b><span>탐색 구간으로 설정 후보를 살펴보고 뒤쪽 검증 구간에서 다시 계산합니다. 검증 거래가 없거나 분석 당시 설정이 변경된 결과는 적용할 수 없습니다. 표본이 작으면 비교 결과를 신뢰하기 어렵습니다.</span></div>
          <Dataset dataset={result.dataset}/>
          </details>
          <details className="ai-evidence-section" open><summary>후보 목록 · {candidates.length}개</summary><div className="ai-candidates">{candidates.map(candidate => {
            const baseline = candidate.id === 'current' || candidate.id === 'baseline';
            const applied = String(selected.applied_candidate_id) === String(candidate.id);
            const eligible = candidateEligible(candidate);
            const risk = !baseline && candidateRiskLabel(candidate.settings, baselineSettings);
            return <article className={`card ai-candidate ${applied ? 'applied' : ''}`} key={candidate.id}><div className="section-head ai-section-head"><h3>{candidate.label || '설정 후보'}</h3>{risk && <span className={`ai-risk-badge risk-${risk.tone}`} title="기존 설정 대비 목표 상승률·손절 폭의 크기를 비교한 값이며 성과 순위가 아닙니다">{risk.text}</span>}{baseline && <span className="ai-mode">기존 설정</span>}{applied && <span className="ai-mode">적용 완료</span>}</div><dl className="ai-setting-list">{AI_SETTING_FIELDS.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{settingText(key, candidate.settings?.[key])}</dd></div>)}</dl><div className="ai-metric-grid"><Metrics title="탐색 구간" values={candidate.train}/><Metrics title="검증 구간" values={candidate.validation}/></div>{!eligible && !baseline && <p className="hint">검증이 충분하지 않아 적용할 수 없는 후보입니다.</p>}{master && !baseline && <button className="quiet" disabled={!eligible || Boolean(pending) || Boolean(selected.applied_candidate_id)} onClick={() => inspectCandidate(candidate)}>{applied ? '이 분석에서 이미 적용됨' : '현재 설정과 비교 후 적용'}</button>}</article>;
          })}</div></details>
          {!candidates.length && <div className="info-note">검증 가능한 설정 후보가 없습니다. 자료와 분석 설명을 확인해 주세요.</div>}
          {candidates.length > 1 && <p className="hint">배지는 기존 설정 대비 목표 상승률·손절 폭의 크기를 비교한 값이며, 성과가 더 낫다는 검증 결과가 아닙니다.</p>}
          {!master && <p className="hint">분석과 비교는 관리자도 볼 수 있지만, 실제 계산 설정 적용은 MASTER 권한만 가능합니다.</p>}
          {proposal && <section className="card ai-confirm" aria-label="계산 설정 적용 확인"><h3>실제 계산 설정을 변경할까요?</h3><p>{marketName(selected.market)} · {proposal.candidate.label || '선택한 후보'}</p><div className="ai-comparison"><div className="ai-comparison-heading"><b>항목</b><b>현재 설정</b><b>변경할 설정</b></div>{AI_SETTING_FIELDS.map(([key, label]) => <div key={key}><span>{label}</span><span>{settingText(key, proposal.current[key])}</span><strong>{settingText(key, proposal.candidate.settings?.[key])}</strong></div>)}</div><ValidationComparison candidate={proposal.candidate} baseline={candidates.find(item => ['current', 'baseline'].includes(item.id))}/><div className="info-note"><b>다음 계산부터 실제 운영에 영향을 줍니다.</b><span>자동매매가 켜져 있으면 이후 추천·매매 판단에 영향을 줄 수 있습니다. AI가 직접 주문하지는 않으며 자동매매의 켜짐/꺼짐 상태도 바꾸지 않습니다.</span></div>{stale && <div className="error" role="alert">분석 이후 현재 설정이 바뀌었습니다. 새 분석을 실행한 뒤 다시 비교해 주세요.</div>}<label className="check ai-consent"><input type="checkbox" checked={confirmed} disabled={stale || pending === 'apply'} onChange={event => setConfirmed(event.target.checked)}/><span>변경 전후 설정과 실제 자동매매에 미치는 영향을 확인했으며, 이 설정을 적용합니다.</span></label><div className="ai-actions"><button className="primary" disabled={!confirmed || stale || Boolean(pending)} onClick={applyCandidate}>{pending === 'apply' ? '설정 적용 중…' : '확인한 설정 적용'}</button><button className="quiet" disabled={pending === 'apply'} onClick={() => {setProposal(null); setConfirmed(false);}}>취소</button></div></section>}
          <details className="ai-evidence-section"><summary>검증의 한계</summary><Notes title="검증의 한계" items={result.limitations}/></details>
          <details className="ai-details"><summary>사용한 자료와 조회 기록</summary><Notes title="데이터 출처" items={result.data_sources}/>{Array.isArray(result.data_sources) && result.data_sources.filter(source => typeof source === 'object' && source !== null).map((source, index) => <p className="ai-source" key={index}>{source.name || source.source || source.provider || source.symbol || source.code || '시장 자료'}{(source.as_of || source.fetched_at || source.end_date) && <span> · {timestamp(source.as_of || source.fetched_at || source.end_date)}</span>}{source.start_date && <span> · 시작 {source.start_date}</span>}{source.bars != null && <span> · {count(source.bars)}개 봉</span>}</p>)}{Array.isArray(result.tool_calls) && result.tool_calls.map((call, index) => <p className="ai-source" key={index}>{typeof call === 'string' ? call : call?.name || call?.tool || '자료 조회'}{call?.status && <span> · {call.status}</span>}</p>)}{!result.data_sources?.length && !result.tool_calls?.length && <p className="hint">제공된 조회 기록이 없습니다.</p>}</details>
          <section className="ai-chat"><div className="ai-chat-thread">{mobile && viewMode==='chat' && <article><div className="ai-chat-user"><b>나</b><p>{selected.prompt}</p></div><div className="ai-chat-assistant"><b>DeepSeek</b><MarkdownAnswer>{result.report}</MarkdownAnswer></div></article>}{conversations.map(message => <article key={message.id}><div className="ai-chat-user"><b>나</b>{message.include_portfolio&&<small>계좌·최근 주문 요약 포함</small>}<p>{message.question}</p></div><div className="ai-chat-assistant"><b>DeepSeek</b>{isAnalysisRunning(message.status) ? <p className="ai-muted">종목·시세·기술 통계·뉴스·백테스트 자료를 확인하며 답변을 작성하고 있습니다…</p> : message.status === 'FAILED' ? <p className="error">{message.error_message || '답변을 완료하지 못했습니다.'}</p> : <><MarkdownAnswer>{message.answer}</MarkdownAnswer>{message.research?.data_sources?.map((source, index) => <div className="ai-news-source" key={index}><b>{source.provider || source.source || source.code || '공개 자료'}</b>{source.query && <span>검색어: {source.query}</span>}{source.articles?.map((article, articleIndex) => <a key={articleIndex} href={article.link} target="_blank" rel="noreferrer">{article.title}<small>{article.source} · {timestamp(article.published_at)}</small></a>)}</div>)}<small className="ai-muted">{count(message.usage_tokens)} 토큰</small></>}</div></article>)}<div ref={chatBottomRef}/></div>{compactChat ? <form className="ai-message-composer ai-compact-composer" onSubmit={askFollowUp}>
              {selected.include_account&&selected.market==='upbit'&&<div className="ai-compact-consent"><button type="button" className="quiet" role="switch" aria-checked={includePortfolio} disabled={chatRunning||Boolean(pending)} onClick={()=>setIncludePortfolio(value=>!value)}>계좌 포함 {includePortfolio?'켜짐':'꺼짐'}</button><button type="button" className="quiet" aria-label="계좌 전송 항목 안내" onClick={()=>setSharingSheet(true)}><Icon name="info"/></button></div>}
              <div className="ai-compact-input"><textarea ref={messageInputRef} rows="1" aria-label="메시지" minLength="1" maxLength="1500" required value={chatQuestion} onChange={event=>setChatQuestion(event.target.value)} placeholder="투자 관련 내용을 물어보세요."/><button className="primary" aria-label="보내기" disabled={!chatQuestion.trim()||chatRunning||Boolean(pending)}><Icon name="send"/></button></div>
            </form> : <form className="form ai-message-composer" onSubmit={askFollowUp}><label><span className="sr-only">메시지</span><textarea rows="3" minLength="1" maxLength="1500" required value={chatQuestion} onChange={event => setChatQuestion(event.target.value)} placeholder="종목 검색, 기술 통계, 뉴스, 백테스트 등 투자 관련 내용을 물어보세요."/><small>{chatQuestion.length} / 1,500자 · Enter는 줄바꿈이며 버튼으로 전송합니다.</small></label>{selected.include_account&&selected.market==='upbit'&&<div><label className="check ai-chat-consent ai-chat-consent-row"><input type="checkbox" checked={includePortfolio} disabled={chatRunning||Boolean(pending)} onChange={event=>setIncludePortfolio(event.target.checked)}/><span>계좌·최근 주문 요약 포함</span></label><details className="ai-data-sharing"><summary>무엇이 전송되나요?</summary><p>이번 질문에 현재 계좌와 최근 주문 100건 요약 포함</p><p>Upbit 잔고·수량·평균 매수가와 주문 상태가 DeepSeek에 전달됩니다. API 키와 주문 번호는 제외됩니다.</p></details></div>}<button className="primary" disabled={!chatQuestion.trim() || chatRunning || Boolean(pending)}>{pending === 'chat' ? '보내는 중…' : chatRunning ? '답변 작성 중…' : '보내기'}</button></form>}</section>
        </>}
      </>}
    </section>}
    {selectedId === null && <section className="ai-chat-empty"><b>새 분석 대화를 준비하고 있습니다.</b><span>위에서 시장과 종목을 고른 뒤 첫 메시지를 보내세요.</span></section>}
    </div></div>
    {confirmDialog && (
      <ConfirmModal
        title={confirmDialog.title}
        message={confirmDialog.message}
        confirmText={confirmDialog.confirmText || '삭제'}
        onConfirm={confirmDialog.onConfirm}
        onClose={() => setConfirmDialog(null)}
      >{confirmDialog.content}</ConfirmModal>
    )}
  </div>;
}
