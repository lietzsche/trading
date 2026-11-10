import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, displayOrderStatus, orderStatus } from './api';
import UsageGuide from './UsageGuide';
import './tokens.css';
import './base.css';
import './layout.css';
import './components.css';
import './dashboard.css';
import './mobile-ux.css';

if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));
}

export const money = v => `₩${Math.round(Number(v || 0)).toLocaleString('ko-KR')}`;
export const date = v => (v ? String(v).replace('T', ' ').slice(0, 19) : '—');

export const CANDLE_INTERVAL_OPTIONS = [
  { value: '30m', label: '30분봉', unit: '봉' },
  { value: '60m', label: '1시간봉', unit: '봉' },
  { value: '240m', label: '4시간봉', unit: '봉' },
  { value: 'days', label: '일봉', unit: '일' },
  { value: 'weeks', label: '주봉', unit: '주' },
];

export function candleIntervalLabel(interval) {
  const found = CANDLE_INTERVAL_OPTIONS.find(o => o.value === interval);
  if (found) return found.label;
  if (interval === '15m') return '15분봉';
  return '일봉';
}

export function BrandLogo({ size = 40, className = '' }) {
  const uid = React.useId ? React.useId().replace(/:/g, '') : 'ma40';
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`brand-logo-svg ${className}`.trim()}
      role="img"
      aria-label="MA40 Auto Trader 로고"
    >
      <defs>
        <linearGradient id={`bg-${uid}`} x1="0" y1="0" x2="512" y2="512" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0E182E" />
          <stop offset="55%" stopColor="#091122" />
          <stop offset="100%" stopColor="#060A14" />
        </linearGradient>
        <radialGradient id={`eg-${uid}`} cx="72%" cy="26%" r="54%">
          <stop offset="0%" stopColor="#10B981" stopOpacity="0.36" />
          <stop offset="100%" stopColor="#10B981" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`c1-${uid}`} x1="0" y1="276" x2="0" y2="375" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60A5FA" />
          <stop offset="100%" stopColor="#2563EB" />
        </linearGradient>
        <linearGradient id={`c2-${uid}`} x1="0" y1="220" x2="0" y2="340" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#22D3EE" />
          <stop offset="100%" stopColor="#0891B2" />
        </linearGradient>
        <linearGradient id={`c3-${uid}`} x1="0" y1="142" x2="0" y2="298" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#34D399" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        <linearGradient id={`mw-${uid}`} x1="95" y1="362" x2="415" y2="112" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="50%" stopColor="#2DD4BF" />
          <stop offset="100%" stopColor="#6EE7B7" />
        </linearGradient>
      </defs>
      <rect x="10" y="10" width="492" height="492" rx="112" fill={`url(#bg-${uid})`} />
      <rect x="10" y="10" width="492" height="492" rx="112" fill={`url(#eg-${uid})`} />
      <rect x="10" y="10" width="492" height="492" rx="112" stroke="#38BDF8" strokeOpacity="0.38" strokeWidth="6" />
      <rect x="145" y="250" width="12" height="158" rx="6" fill="#60A5FA" fillOpacity="0.9" />
      <rect x="124" y="286" width="54" height="90" rx="14" fill={`url(#c1-${uid})`} />
      <rect x="241" y="182" width="12" height="194" rx="6" fill="#67E8F9" fillOpacity="0.92" />
      <rect x="220" y="224" width="54" height="114" rx="14" fill={`url(#c2-${uid})`} />
      <rect x="338" y="99" width="12" height="240" rx="6" fill="#6EE7B7" fillOpacity="0.95" />
      <rect x="317" y="145" width="54" height="152" rx="14" fill={`url(#c3-${uid})`} />
      <path d="M99 357 C196 352 279 265 378 156" stroke="#070D19" strokeWidth="44" strokeLinecap="round" />
      <polygon points="432,104 330,118 370,162 396,204" fill="#070D19" />
      <path d="M99 357 C196 352 279 265 378 156" stroke={`url(#mw-${uid})`} strokeWidth="30" strokeLinecap="round" />
      <polygon points="424,111 336,120 373,161 392,198" fill="#6EE7B7" />
      <circle cx="288" cy="249" r="24" fill="#FFFFFF" stroke="#10B981" strokeWidth="9" />
    </svg>
  );
}

export function usePwaInstall() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstalled, setIsInstalled] = useState(() => {
    if (typeof window === 'undefined') return false;
    const standaloneMatch = window.matchMedia && window.matchMedia('(display-mode: standalone)').matches;
    const iosStandalone = window.navigator && window.navigator.standalone === true;
    return Boolean(standaloneMatch || iosStandalone);
  });

  const isIos =
    typeof navigator !== 'undefined' && /iphone|ipad|ipod/i.test(String(navigator.userAgent || ''));

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onBeforeInstall = e => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    const onAppInstalled = () => {
      setIsInstalled(true);
      setDeferredPrompt(null);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    window.addEventListener('appinstalled', onAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const triggerInstall = useCallback(async () => {
    if (!deferredPrompt || typeof deferredPrompt.prompt !== 'function') {
      return { outcome: 'manual' };
    }
    try {
      await deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice && choice.outcome === 'accepted') {
        setIsInstalled(true);
        setDeferredPrompt(null);
      }
      return choice || { outcome: 'dismissed' };
    } catch (_) {
      return { outcome: 'error' };
    }
  }, [deferredPrompt]);

  return {
    canNativeInstall: Boolean(deferredPrompt),
    isInstalled,
    isIos,
    triggerInstall,
  };
}

export function AppInstallModal({ open, onClose, pwa }) {
  const [installNotice, setInstallNotice] = useState('');
  if (!open) return null;

  const { canNativeInstall, isInstalled, isIos, triggerInstall } = pwa || {};

  async function handleDirectInstall() {
    setInstallNotice('');
    if (canNativeInstall && triggerInstall) {
      const res = await triggerInstall();
      if (res?.outcome === 'accepted') {
        setInstallNotice('앱 설치가 시작되었습니다. 홈 화면 또는 바탕화면에서 실행해 보세요!');
      }
      return;
    }
    if (isIos) {
      setInstallNotice('아이폰·아이패드 Safari에서는 아래 안내대로 [공유] → [홈 화면에 추가]를 눌러 설치해 주세요.');
    } else {
      setInstallNotice('브라우저 우측 상단 메뉴(⋮)에서 [앱 설치] 또는 [홈 화면에 추가]를 선택해 바로 설치할 수 있습니다.');
    }
  }

  return (
    <div
      className="safe-sell-overlay pwa-install-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="MA40 트레이더 앱 다운로드 및 설치"
    >
      <div className="safe-sell-modal pwa-install-modal">
        <div className="safe-sell-header">
          <div className="pwa-modal-brand-head">
            <BrandLogo size={60} className="pwa-modal-logo" />
            <div>
              <span className="pwa-store-badge">OFFICIAL WEB APP · PWA</span>
              <h3>MA40 오토 트레이더 앱 다운로드</h3>
              <p className="pwa-modal-sub">
                모바일 홈 화면과 PC 바탕화면에 전용 앱으로 설치해 주소창 없는 풀스크린으로 빠르게 실행하세요.
              </p>
            </div>
          </div>
          <button type="button" className="safe-sell-close-btn" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>

        {/* Visual App Store Preview Showcase */}
        <div className="pwa-preview-showcase" aria-hidden="true">
          <div className="pwa-preview-device">
            <div className="pwa-preview-topbar">
              <BrandLogo size={24} />
              <span>MA40 트레이더 · 독립 실행 모드</span>
              <span className="pwa-preview-live-dot">LIVE</span>
            </div>
            <div className="pwa-preview-metrics">
              <div className="pwa-preview-chip positive">
                <small>백테스트 수익률 1순위</small>
                <strong>+38.40%</strong>
              </div>
              <div className="pwa-preview-chip cyan">
                <small>마이너스 수익률 차단</small>
                <strong>안전 보호 ON</strong>
              </div>
              <div className="pwa-preview-chip neutral">
                <small>다중 타임프레임</small>
                <strong>30분~주봉</strong>
              </div>
            </div>
          </div>
          <div className="pwa-feature-pills">
            <span>⚡ 1초 즉시 실행</span>
            <span>📱 풀스크린 전용 UI</span>
            <span>🛡️ 마이너스 수익률 차단</span>
            <span>📊 실시간 백테스트 정렬</span>
          </div>
        </div>

        <div className="pwa-install-cta-box">
          {isInstalled ? (
            <div className="pwa-installed-badge" role="status">
              ✓ 현재 기기에 앱이 설치되어 있거나 앱 모드로 실행 중입니다.
            </div>
          ) : (
            <button type="button" className="primary pwa-download-cta-btn" onClick={handleDirectInstall}>
              {canNativeInstall ? '📲 지금 바로 앱 다운로드 (원클릭 설치)' : '📲 앱 다운로드 및 홈 화면 설치하기'}
            </button>
          )}
          {installNotice && (
            <p className="pwa-install-feedback" role="status">
              {installNotice}
            </p>
          )}
        </div>

        <div className="pwa-guide-grid">
          <article className={`pwa-guide-card ${!isIos ? 'recommended' : ''}`}>
            <div className="pwa-guide-card-head">
              <strong>Android · PC (Chrome / Edge / 삼성 인터넷)</strong>
              {!isIos && <span className="badge">현재 기기 추천</span>}
            </div>
            <ol>
              <li>
                위 <b>앱 다운로드</b> 버튼을 누르면 뜨는 설치 팝업에서 <b>[설치]</b>를 누릅니다.
              </li>
              <li>
                팝업이 뜨지 않으면 브라우저 우측 상단 메뉴(<b>⋮</b>) 또는 주소창 우측의 <b>[앱 설치]</b> 아이콘을 선택하세요.
              </li>
            </ol>
          </article>

          <article className={`pwa-guide-card ${isIos ? 'recommended' : ''}`}>
            <div className="pwa-guide-card-head">
              <strong>iPhone · iPad (Safari 브라우저)</strong>
              {isIos && <span className="badge">현재 기기 추천</span>}
            </div>
            <ol>
              <li>
                Safari 하단(또는 상단) 도구모음의 <b>공유 버튼 [↑]</b>을 탭합니다.
              </li>
              <li>
                메뉴를 내려 <b>[홈 화면에 추가 (+)]</b>를 누른 뒤 우측 상단 <b>[추가]</b>를 탭하면 설치가 완료됩니다.
              </li>
            </ol>
          </article>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
          <button type="button" className="quiet" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

export function Login({ onLogin }) {
  const [id, setId] = useState('');
  const [pw, setPw] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [joining, setJoining] = useState(false);
  const [canJoin, setCanJoin] = useState(false);
  const [showInstallModal, setShowInstallModal] = useState(false);
  const pwa = usePwaInstall();

  useEffect(() => {
    api('/auth/config')
      .then(x => setCanJoin(x.signup_enabled === true))
      .catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError('');
    try {
      if (joining) {
        await api('/auth/join', {
          method: 'POST',
          body: JSON.stringify({ login_id: id, password: pw, name }),
        });
        setJoining(false);
        setPw('');
        return;
      }
      await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ login_id: id, password: pw }),
      });
      onLogin();
    } catch (x) {
      setError(x.message);
    }
  }

  return (
    <main className="login">
      <form className="login-form" onSubmit={submit}>
        <div className="login-brand-hero">
          <BrandLogo size={54} className="login-brand-logo" />
          <div>
            <small className="eyebrow">UPBIT MA40 AUTO TRADER</small>
            <h1>{joining ? '첫 계정 만들기' : '40일 이동평균 자동매매'}</h1>
            <p>{joining ? '로컬 운영 계정을 생성합니다.' : '하나의 전략만, 상태는 투명하게 확인합니다.'}</p>
          </div>
        </div>
        {joining && (
          <label>
            이름
            <input value={name} onChange={e => setName(e.target.value)} required />
          </label>
        )}
        <label>
          아이디
          <input autoFocus value={id} onChange={e => setId(e.target.value)} required />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            value={pw}
            onChange={e => setPw(e.target.value)}
            minLength={joining ? 8 : 1}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary">{joining ? '계정 생성' : '로그인'}</button>
        {canJoin && (
          <button
            type="button"
            className="quiet"
            onClick={() => {
              setJoining(!joining);
              setError('');
            }}
          >
            {joining ? '로그인으로 돌아가기' : '처음 실행인가요? 계정 만들기'}
          </button>
        )}
        {!pwa.isInstalled && (
          <button
            type="button"
            className="quiet pwa-login-install-btn"
            onClick={() => setShowInstallModal(true)}
          >
            📲 모바일·PC 전용 앱 다운로드 (홈 화면 설치)
          </button>
        )}
      </form>
      <AppInstallModal open={showInstallModal} onClose={() => setShowInstallModal(false)} pwa={pwa} />
    </main>
  );
}

export const REC_SORT_OPTIONS = [
  { value: 'bt_return_desc', label: '백테스트 수익률 높은순' },
  { value: 'spread_desc', label: '괴리율 높은순 (기본)' },
  { value: 'bt_excess_desc', label: '초과수익률(단순보유 대비) 높은순' },
  { value: 'bt_mdd_asc', label: '최대낙폭(MDD) 낮은순' },
  { value: 'bt_win_rate_desc', label: '백테스트 승률 높은순' },
];

export function computeSpreadPct(item) {
  if (!item) return null;
  if (item.spread_pct != null && Number.isFinite(Number(item.spread_pct))) {
    return Number(item.spread_pct);
  }
  const setting = Number(item.setting_price);
  const temp = Number(item.temp_price);
  if (!Number.isFinite(setting) || setting <= 0 || !Number.isFinite(temp)) return null;
  return ((temp - setting) * 100) / setting;
}

export function sortRecommendations(items, sortBy = 'spread_desc') {
  const list = Array.isArray(items) ? [...items] : [];
  const toValidNum = val => (val != null && Number.isFinite(Number(val)) ? Number(val) : null);

  return list.sort((a, b) => {
    const spreadA = computeSpreadPct(a) ?? -Infinity;
    const spreadB = computeSpreadPct(b) ?? -Infinity;

    if (sortBy === 'bt_return_desc') {
      const va = toValidNum(a.bt_return_pct);
      const vb = toValidNum(b.bt_return_pct);
      if (va == null && vb == null) return spreadB - spreadA;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (vb !== va) return vb - va;
      return spreadB - spreadA;
    }
    if (sortBy === 'bt_excess_desc') {
      const va = toValidNum(a.bt_excess_pct);
      const vb = toValidNum(b.bt_excess_pct);
      if (va == null && vb == null) return spreadB - spreadA;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (vb !== va) return vb - va;
      return spreadB - spreadA;
    }
    if (sortBy === 'bt_mdd_asc') {
      const va = toValidNum(a.bt_mdd_pct);
      const vb = toValidNum(b.bt_mdd_pct);
      if (va == null && vb == null) return spreadB - spreadA;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (va !== vb) return va - vb;
      return spreadB - spreadA;
    }
    if (sortBy === 'bt_win_rate_desc') {
      const va = toValidNum(a.bt_win_rate_pct);
      const vb = toValidNum(b.bt_win_rate_pct);
      if (va == null && vb == null) return spreadB - spreadA;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (vb !== va) return vb - va;
      return spreadB - spreadA;
    }
    return spreadB - spreadA;
  });
}

export function filterRecommendations(items, filters = {}, isAutoEnabledFn = r => Boolean(r?.auto_trade)) {
  const {
    hideNegativeBt = false,
    onlyPositiveExcess = false,
    lowMddOnly = false,
    onlyAutoEnabled = false,
    searchQuery = '',
  } = filters;
  const q = String(searchQuery || '').trim().toLowerCase();

  return (Array.isArray(items) ? items : []).filter(r => {
    if (hideNegativeBt && r.bt_return_pct != null && Number(r.bt_return_pct) < 0) {
      return false;
    }
    if (onlyPositiveExcess && !(r.bt_excess_pct != null && Number(r.bt_excess_pct) > 0)) {
      return false;
    }
    if (lowMddOnly && !(r.bt_mdd_pct != null && Number(r.bt_mdd_pct) <= 20)) {
      return false;
    }
    if (onlyAutoEnabled && !isAutoEnabledFn(r)) {
      return false;
    }
    if (q) {
      const code = String(r.code || r.market || '').toLowerCase();
      const name = String(r.name || '').toLowerCase();
      if (!code.includes(q) && !name.includes(q)) {
        return false;
      }
    }
    return true;
  });
}

export function computeEnabledRanks(sortedSignals, isAutoEnabledFn = r => Boolean(r?.auto_trade), excludeNegativeBt = false) {
  const enabledRankByCode = {};
  const blockedNegativeByCode = {};
  let rank = 0;

  (Array.isArray(sortedSignals) ? sortedSignals : []).forEach(r => {
    const code = r.code || r.market;
    if (!code || !isAutoEnabledFn(r)) return;
    const isNegBt = r.bt_return_pct != null && Number(r.bt_return_pct) < 0;
    if ((excludeNegativeBt && isNegBt) || r.auto_trade_excluded_reason === 'negative_bt') {
      blockedNegativeByCode[code] = true;
      return;
    }
    rank += 1;
    enabledRankByCode[code] = rank;
  });

  return { enabledRankByCode, blockedNegativeByCode };
}

export async function batchUpdateAutoTradeMarkets(codes, autoTrade = true) {
  const targets = Array.from(new Set((codes || []).filter(Boolean)));
  if (!targets.length) return null;
  return api('/upbit/auto-markets', {
    method: 'PUT',
    body: JSON.stringify({
      market: targets[0],
      markets: targets,
      auto_trade: Boolean(autoTrade),
    }),
  });
}

export function BacktestEquityCurve({ curve, initialCapital = 1000000 }) {
  if (!Array.isArray(curve) || curve.length < 2) return null;
  const equities = curve.map(p => Number(p.equity || 0)).filter(Number.isFinite);
  if (equities.length < 2) return null;
  const baseCap = Number(initialCapital || equities[0] || 1000000);
  const minEq = Math.min(...equities, baseCap);
  const maxEq = Math.max(...equities, baseCap);
  const span = Math.max(1, maxEq - minEq);
  const width = 600;
  const height = 160;
  const padY = 16;
  const usableH = height - padY * 2;

  const toY = val => padY + usableH - ((val - minEq) / span) * usableH;
  const toX = idx => (idx / (curve.length - 1)) * width;

  const points = curve
    .map((pt, idx) => `${toX(idx).toFixed(1)},${toY(Number(pt.equity || 0)).toFixed(1)}`)
    .join(' ');
  const baselineY = toY(baseCap).toFixed(1);
  const isProfit = equities[equities.length - 1] >= baseCap;
  const strokeColor = isProfit ? 'var(--price-up, #e06c75)' : 'var(--price-down, #4d88ff)';
  const firstDate = curve[0]?.date || '';
  const lastDate = curve[curve.length - 1]?.date || '';

  return (
    <section className="bt-curve-card">
      <div className="bt-curve-head">
        <h4>자산 추이 곡선 (Equity Curve)</h4>
        <div className="bt-curve-range">
          <span>최저 {money(minEq)}</span>
          <span>기준 {money(baseCap)}</span>
          <span>최고 {money(maxEq)}</span>
        </div>
      </div>
      <div className="bt-curve-svg-wrap">
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="bt-curve-svg" role="img" aria-label="백테스트 자산 추이 곡선">
          <line
            x1="0"
            y1={baselineY}
            x2={width}
            y2={baselineY}
            stroke="var(--text-tertiary, #888)"
            strokeWidth="1.2"
            strokeDasharray="4 4"
          />
          <polyline
            fill="none"
            stroke={strokeColor}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={points}
          />
        </svg>
      </div>
      <div className="bt-curve-foot">
        <small>{firstDate}</small>
        <small>{lastDate}</small>
      </div>
    </section>
  );
}

export function Monitor({ data, refresh, initialFilters = {} }) {
  const s = data.safety || {};
  const perf = data.performance || {};
  const strategyCfg = data.strategy_settings || {};
  const signalCollection = data.signal_collection || {};
  const globalCandleInterval = strategyCfg.candle_interval || 'days';
  const globalIntervalText = candleIntervalLabel(globalCandleInterval);
  const globalMaPeriod = Number(strategyCfg.ma_period || 40);
  const assets = data.assets || [];
  const rawSignals = data.recommendations || [];
  const unresolvedCount = Array.isArray(s.unresolved_orders)
    ? s.unresolved_orders.length
    : Number(s.unresolved_orders || 0);
  const isBlocked = s.level === 'blocked' || unresolvedCount > 0;

  const [reconciling, setReconciling] = useState(false);
  const [reconcileMsg, setReconcileMsg] = useState('');
  const [targetSellAsset, setTargetSellAsset] = useState(null);
  const [selling, setSelling] = useState(false);
  const [sellMsg, setSellMsg] = useState('');
  const [btTarget, setBtTarget] = useState(null);
  const [btResult, setBtResult] = useState(null);
  const [btBusy, setBtBusy] = useState(false);
  const [btError, setBtError] = useState('');
  const [btUsedParams, setBtUsedParams] = useState(null);
  const [autoTradeOverrides, setAutoTradeOverrides] = useState({});
  const [togglingMarkets, setTogglingMarkets] = useState({});
  const [clearingBatch, setClearingBatch] = useState(false);
  const [autoTradeError, setAutoTradeError] = useState('');
  const [recollecting, setRecollecting] = useState(false);

  // Batch backtest enrichment state
  const [btBatchMap, setBtBatchMap] = useState({});
  const [btBatchBusy, setBtBatchBusy] = useState(false);
  const autoBtTriggeredKeyRef = useRef('');

  // Recommendation sorting & filtering state
  const [sortBy, setSortBy] = useState(strategyCfg.sort_by || 'spread_desc');
  const [excludeNegativeBt, setExcludeNegativeBt] = useState(Boolean(strategyCfg.exclude_negative_bt));
  const [hideNegativeBt, setHideNegativeBt] = useState(Boolean(initialFilters.hideNegativeBt));
  const [onlyPositiveExcess, setOnlyPositiveExcess] = useState(Boolean(initialFilters.onlyPositiveExcess));
  const [lowMddOnly, setLowMddOnly] = useState(Boolean(initialFilters.lowMddOnly));
  const [onlyAutoEnabled, setOnlyAutoEnabled] = useState(Boolean(initialFilters.onlyAutoEnabled));
  const [searchQuery, setSearchQuery] = useState(initialFilters.searchQuery || '');

  useEffect(() => {
    if (strategyCfg.sort_by) {
      setSortBy(strategyCfg.sort_by);
    }
  }, [strategyCfg.sort_by]);

  useEffect(() => {
    if (strategyCfg.exclude_negative_bt !== undefined) {
      setExcludeNegativeBt(Boolean(strategyCfg.exclude_negative_bt));
    }
  }, [strategyCfg.exclude_negative_bt]);

  useEffect(() => {
    if (!signalCollection.running || !refresh) return undefined;
    const timer = setInterval(() => {
      refresh();
    }, 2000);
    return () => clearInterval(timer);
  }, [signalCollection.running, refresh]);

  const enrichedSignals = rawSignals.map(r => {
    const code = r.code || r.market;
    const cached = code ? btBatchMap[code] : null;
    const spreadPct = computeSpreadPct(r);
    if (!cached) {
      return { ...r, spread_pct: spreadPct };
    }
    return {
      ...r,
      spread_pct: spreadPct,
      bt_return_pct: cached.bt_return_pct ?? r.bt_return_pct ?? null,
      bt_benchmark_pct: cached.bt_benchmark_pct ?? r.bt_benchmark_pct ?? null,
      bt_excess_pct: cached.bt_excess_pct ?? r.bt_excess_pct ?? null,
      bt_mdd_pct: cached.bt_mdd_pct ?? r.bt_mdd_pct ?? null,
      bt_trade_count: cached.bt_trade_count ?? r.bt_trade_count ?? null,
      bt_win_rate_pct: cached.bt_win_rate_pct ?? r.bt_win_rate_pct ?? null,
      bt_updated_at: cached.bt_updated_at ?? r.bt_updated_at ?? null,
    };
  });

  const signals = sortRecommendations(enrichedSignals, sortBy);

  async function runBatchBacktest(force = false) {
    if (btBatchBusy || !rawSignals.length) return;
    const markets = rawSignals.map(r => r.code || r.market).filter(Boolean);
    if (!markets.length) return;
    setBtBatchBusy(true);
    if (force) setAutoTradeError('');
    try {
      const res = await api('/backtest/batch', {
        method: 'POST',
        body: JSON.stringify({ markets, force: Boolean(force) }),
      });
      if (res && res.items && typeof res.items === 'object') {
        if (Array.isArray(res.items)) {
          const mapped = {};
          res.items.forEach(item => {
            if (item && item.code) mapped[item.code] = item;
          });
          setBtBatchMap(prev => ({ ...prev, ...mapped }));
        } else {
          setBtBatchMap(prev => ({ ...prev, ...res.items }));
        }
      }
      if (refresh && res && res.updated_count > 0) {
        await refresh();
      }
    } catch (err) {
      if (force) {
        setAutoTradeError(err.message || '일괄 백테스트 계산에 실패했습니다.');
      }
    } finally {
      setBtBatchBusy(false);
    }
  }

  useEffect(() => {
    if (signalCollection.running || btBatchBusy || !enrichedSignals.length) return;
    const missingCodes = enrichedSignals
      .filter(r => r.bt_return_pct == null)
      .map(r => r.code || r.market)
      .filter(Boolean)
      .sort();
    if (!missingCodes.length) return;
    const key = `${globalCandleInterval}:${globalMaPeriod}:${missingCodes.join(',')}`;
    if (autoBtTriggeredKeyRef.current === key) return;
    autoBtTriggeredKeyRef.current = key;
    runBatchBacktest(false);
  }, [enrichedSignals, signalCollection.running, btBatchBusy, globalCandleInterval, globalMaPeriod]);

  async function updateRecommendationPrefs(nextSortBy, nextExcludeNegativeBt) {
    setSortBy(nextSortBy);
    setExcludeNegativeBt(Boolean(nextExcludeNegativeBt));
    setAutoTradeError('');
    try {
      await api('/upbit/recommendation-prefs', {
        method: 'PUT',
        body: JSON.stringify({
          sort_by: nextSortBy,
          exclude_negative_bt: Boolean(nextExcludeNegativeBt),
        }),
      });
      if (refresh) await refresh();
    } catch (err) {
      setAutoTradeError(err.message || '추천 정렬 및 안전 설정 저장에 실패했습니다.');
    }
  }

  async function handleManualRecollect() {
    if (recollecting || signalCollection.running) return;
    setRecollecting(true);
    setAutoTradeError('');
    try {
      await api('/upbit/recollect', { method: 'POST' });
      if (refresh) await refresh();
    } catch (err) {
      setAutoTradeError(err.message || '신호 재계산 요청에 실패했습니다.');
    } finally {
      setRecollecting(false);
    }
  }

  const autoTradeMarketSet = new Set(Array.isArray(data.auto_trade_markets) ? data.auto_trade_markets : []);

  function isMarketAutoEnabled(item) {
    const code = typeof item === 'string' ? item : (item.code || item.market);
    if (Object.prototype.hasOwnProperty.call(autoTradeOverrides, code)) {
      return autoTradeOverrides[code];
    }
    if (typeof item === 'object' && item !== null && 'auto_trade' in item) {
      return Boolean(item.auto_trade);
    }
    return autoTradeMarketSet.has(code);
  }

  async function toggleMarketAutoTrade(item, forcedState = null) {
    const code = typeof item === 'string' ? item : (item.code || item.market);
    if (!code || togglingMarkets[code]) return;
    const nextState = forcedState !== null ? Boolean(forcedState) : !isMarketAutoEnabled(item);
    setAutoTradeError('');
    setTogglingMarkets(prev => ({ ...prev, [code]: true }));
    setAutoTradeOverrides(prev => ({ ...prev, [code]: nextState }));
    try {
      await api('/upbit/auto-markets', {
        method: 'PUT',
        body: JSON.stringify({ market: code, auto_trade: nextState }),
      });
      if (refresh) await refresh();
    } catch (err) {
      setAutoTradeOverrides(prev => ({ ...prev, [code]: !nextState }));
      setAutoTradeError(err.message || '자동매수 설정 변경에 실패했습니다.');
    } finally {
      setTogglingMarkets(prev => {
        const next = { ...prev };
        delete next[code];
        return next;
      });
    }
  }

  async function enableAutoTradeMarkets(codes) {
    const targets = Array.from(new Set((codes || []).filter(Boolean)));
    if (!targets.length || clearingBatch) return;
    setAutoTradeError('');
    setClearingBatch(true);
    const prevOverrides = { ...autoTradeOverrides };
    setAutoTradeOverrides(prev => {
      const next = { ...prev };
      targets.forEach(c => {
        next[c] = true;
      });
      return next;
    });
    try {
      await batchUpdateAutoTradeMarkets(targets, true);
      if (refresh) await refresh();
    } catch (err) {
      setAutoTradeOverrides(prevOverrides);
      setAutoTradeError(err.message || '자동매수 일괄 허용에 실패했습니다.');
    } finally {
      setClearingBatch(false);
    }
  }

  async function clearAutoTradeMarkets(codes) {
    const targets = Array.from(new Set((codes || []).filter(Boolean)));
    if (!targets.length || clearingBatch) return;
    setAutoTradeError('');
    setClearingBatch(true);
    const prevOverrides = { ...autoTradeOverrides };
    setAutoTradeOverrides(prev => {
      const next = { ...prev };
      targets.forEach(c => {
        next[c] = false;
      });
      return next;
    });
    try {
      await batchUpdateAutoTradeMarkets(targets, false);
      if (refresh) await refresh();
    } catch (err) {
      setAutoTradeOverrides(prevOverrides);
      setAutoTradeError(err.message || '자동매수 일괄 해제에 실패했습니다.');
    } finally {
      setClearingBatch(false);
    }
  }

  const activeEnabledSignals = signals.filter(r => isMarketAutoEnabled(r));
  const enabledSignalCount = activeEnabledSignals.length;
  const { enabledRankByCode, blockedNegativeByCode } = computeEnabledRanks(
    signals,
    isMarketAutoEnabled,
    excludeNegativeBt
  );

  const filteredSignals = filterRecommendations(
    signals,
    {
      hideNegativeBt,
      onlyPositiveExcess,
      lowMddOnly,
      onlyAutoEnabled,
      searchQuery,
    },
    isMarketAutoEnabled
  );

  const negativeBtCount = signals.filter(r => r.bt_return_pct != null && Number(r.bt_return_pct) < 0).length;
  const negativeEnabledCodes = activeEnabledSignals
    .filter(r => r.bt_return_pct != null && Number(r.bt_return_pct) < 0)
    .map(r => r.code || r.market)
    .filter(Boolean);
  const positiveFilteredCodes = filteredSignals
    .filter(r => r.bt_return_pct != null && Number(r.bt_return_pct) >= 0)
    .map(r => r.code || r.market)
    .filter(Boolean);
  const top5CandidateCodes = filteredSignals
    .filter(r => !((hideNegativeBt || excludeNegativeBt) && r.bt_return_pct != null && Number(r.bt_return_pct) < 0))
    .slice(0, 5)
    .map(r => r.code || r.market)
    .filter(Boolean);
  const hasActiveFilter =
    hideNegativeBt || onlyPositiveExcess || lowMddOnly || onlyAutoEnabled || searchQuery.trim() !== '';

  function resetFilters() {
    setHideNegativeBt(false);
    setOnlyPositiveExcess(false);
    setLowMddOnly(false);
    setOnlyAutoEnabled(false);
    setSearchQuery('');
  }

  const activeSignalCodeSet = new Set(signals.map(r => r.code || r.market).filter(Boolean));
  const rawInactiveAuto = Array.isArray(data.inactive_auto_trade_items) ? data.inactive_auto_trade_items : [];
  const inactiveByCode = new Map();
  rawInactiveAuto.forEach(item => {
    const code = item.code || item.market;
    if (code && !activeSignalCodeSet.has(code)) {
      inactiveByCode.set(code, item);
    }
  });
  autoTradeMarketSet.forEach(code => {
    if (code && !activeSignalCodeSet.has(code) && !inactiveByCode.has(code)) {
      inactiveByCode.set(code, { code, name: code, ma_period: globalMaPeriod, auto_trade: true });
    }
  });
  const inactiveAutoItems = Array.from(inactiveByCode.values()).filter(item => isMarketAutoEnabled(item));
  const totalAutoEnabledCount = enabledSignalCount + inactiveAutoItems.length;
  const allEnabledCodes = [
    ...activeEnabledSignals.map(r => r.code || r.market),
    ...inactiveAutoItems.map(r => r.code || r.market),
  ].filter(Boolean);

  const sellableHeldCoins = assets.filter(
    a => a.currency !== 'KRW' && !a.unsellable_reason && Number(a.quantity || a.balance || 0) > 0
  );

  async function runItemBacktest(item) {
    const code = item.code || item.market;
    const candleInterval = item.candle_interval || strategyCfg.candle_interval || 'days';
    const maPeriod = Number(item.ma_period || strategyCfg.ma_period || 40);
    const days = Math.min(200, Math.max(60, maPeriod + 2, Number(strategyCfg.days || 180)));
    const initialCapital = Number(strategyCfg.initial_capital || 1000000);
    const feeBps = Number(strategyCfg.fee_bps ?? 5);
    const slippageBps = Number(strategyCfg.slippage_bps ?? 10);
    const params = {
      market: code,
      candle_interval: candleInterval,
      ma_period: maPeriod,
      days,
      initial_capital: initialCapital,
      fee_bps: feeBps,
      slippage_bps: slippageBps,
    };
    setBtTarget({ code, name: item.name || code });
    setBtUsedParams(params);
    setBtResult(null);
    setBtError('');
    setBtBusy(true);
    try {
      const res = await api('/backtest', {
        method: 'POST',
        body: JSON.stringify(params),
      });
      setBtResult(res);
      if (res && code) {
        setBtBatchMap(prev => ({
          ...prev,
          [code]: {
            bt_return_pct: res.return_pct ?? null,
            bt_benchmark_pct: res.benchmark_return_pct ?? null,
            bt_excess_pct: res.excess_return_pct ?? null,
            bt_mdd_pct: res.max_drawdown_pct ?? null,
            bt_trade_count: res.trade_count ?? null,
            bt_win_rate_pct: res.win_rate_pct ?? null,
            bt_updated_at: new Date().toISOString(),
          },
        }));
      }
    } catch (err) {
      setBtError(err.message || '백테스트 실행에 실패했습니다.');
    } finally {
      setBtBusy(false);
    }
  }

  async function handleReconcile() {
    setReconciling(true);
    setReconcileMsg('');
    try {
      await api('/upbit/auto-orders/reconcile', { method: 'POST' });
      setReconcileMsg('주문 상태가 동기화되었습니다.');
      if (refresh) await refresh();
    } catch (err) {
      setReconcileMsg(err.message || '재확인에 실패했습니다.');
    } finally {
      setReconciling(false);
    }
  }

  async function handleEmergencySell() {
    if (!targetSellAsset) return;
    const marketCode = `KRW-${targetSellAsset.currency}`;
    setSelling(true);
    setSellMsg('');
    try {
      await api('/upbit/orders/market-sell', {
        method: 'POST',
        body: JSON.stringify({
          market: marketCode,
          expected_available_quantity: String(targetSellAsset.balance || targetSellAsset.quantity || 0),
          confirm: true,
          keep_auto: true,
        }),
      });
      setAutoTradeOverrides(prev => ({ ...prev, [marketCode]: false }));
      setTargetSellAsset(null);
      if (refresh) await refresh();
    } catch (err) {
      setSellMsg(err.message || '긴급 매도 실패');
    } finally {
      setSelling(false);
    }
  }

  return (
    <>
      {/* 1. Unconfirmed Order Warning Banner & Reconcile Button */}
      {isBlocked && (
        <section
          className="status-banner blocked"
          role="alert"
          style={{
            border: '2px solid var(--price-up, #e06c75)',
            background: 'var(--state-danger-surface, rgba(224, 108, 117, 0.15))',
            marginBottom: '16px',
          }}
        >
          <div>
            <small style={{ color: 'var(--price-up, #e06c75)', fontWeight: 700 }}>⚠️ 주문 미확인 경고</small>
            <h2 style={{ color: 'var(--text-primary)' }}>
              {s.summary || '미확인 주문으로 인해 자동매매가 일시 중단되었습니다.'}
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              미확인 주문 수: <b>{unresolvedCount}건</b>. 업비트와 주문 상태를 동기화하여 자동매매를 재개할 수 있습니다.
            </p>
            {reconcileMsg && (
              <p style={{ margin: '6px 0 0', fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>
                {reconcileMsg}
              </p>
            )}
          </div>
          <button
            type="button"
            className="danger"
            disabled={reconciling}
            onClick={handleReconcile}
          >
            {reconciling ? '동기화 중…' : '주문 상태 재확인(Reconcile)'}
          </button>
        </section>
      )}

      {/* General Status Banner */}
      <section className={`status-banner ${s.level || 'neutral'}`}>
        <div>
          <small>자동매매 상태</small>
          <h2>{s.summary || '상태 확인 중'}</h2>
        </div>
        <button type="button" className="quiet" onClick={refresh}>
          새로고침
        </button>
      </section>

      {/* 2. Portfolio Performance & Metrics Grid */}
      <section className="metric-grid">
        <article className="card">
          <small>총 평가액</small>
          <strong>{money(data.total_valuation)}</strong>
        </article>
        <article className="card">
          <small>총매수금액</small>
          <strong>{perf.invested != null ? money(perf.invested) : '—'}</strong>
        </article>
        <article className="card">
          <small>평가손익 (수익률)</small>
          <strong className={perf.unrealized_profit > 0 ? 'price-up' : perf.unrealized_profit < 0 ? 'price-down' : ''}>
            {perf.unrealized_profit != null ? `${perf.unrealized_profit > 0 ? '+' : ''}${money(perf.unrealized_profit)}` : '—'}
            {perf.unrealized_rate != null && (
              <span style={{ fontSize: 'var(--text-xs)', marginLeft: '6px' }}>
                ({perf.unrealized_rate > 0 ? '+' : ''}{Number(perf.unrealized_rate).toFixed(2)}%)
              </span>
            )}
          </strong>
        </article>
        <article className="card">
          <small>당일 변동금액 (변동률)</small>
          <strong className={perf.today_change > 0 ? 'price-up' : perf.today_change < 0 ? 'price-down' : ''}>
            {perf.today_change != null ? `${perf.today_change > 0 ? '+' : ''}${money(perf.today_change)}` : '—'}
            {perf.today_change_rate != null && (
              <span style={{ fontSize: 'var(--text-xs)', marginLeft: '6px' }}>
                ({perf.today_change_rate > 0 ? '+' : ''}{Number(perf.today_change_rate).toFixed(2)}%)
              </span>
            )}
          </strong>
        </article>
        <article className="card">
          <small>이동평균 매수 신호 ({globalIntervalText} MA{globalMaPeriod})</small>
          <strong>
            {signals.length}개
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 600 }}>
              (자동매수 {enabledSignalCount}개{inactiveAutoItems.length > 0 ? ` · 신호이탈 ${inactiveAutoItems.length}개` : ''})
            </span>
          </strong>
        </article>
        <article className="card">
          <small>오늘 체결</small>
          <strong>{data.today_executed_count || 0}건</strong>
        </article>
        <article className="card">
          <small>신호 갱신</small>
          <strong>{date(s.price_updated_at)}</strong>
        </article>
      </section>

      {/* Signal Candidates */}
      <section>
        <div className="section-head" style={{ flexWrap: 'wrap' }}>
          <h2>현재 이동평균 신호 ({globalIntervalText} MA{globalMaPeriod})</h2>
          <div className="signal-head-controls">
            <span className={`status-pill ${enabledSignalCount > 0 ? 'on' : inactiveAutoItems.length > 0 ? 'warn' : 'off'}`}>
              {enabledSignalCount > 0 && inactiveAutoItems.length > 0
                ? `자동매수 허용 ${totalAutoEnabledCount}종목 (활성 ${enabledSignalCount} · 신호이탈 ${inactiveAutoItems.length})`
                : enabledSignalCount > 0
                ? `자동매수 허용 ${enabledSignalCount}종목`
                : inactiveAutoItems.length > 0
                ? `자동매수 대기 ${inactiveAutoItems.length}종목 (현재 신호 이탈)`
                : '자동매수 허용 종목 없음 (매수 대기)'}
            </span>
            {signals.length > 0 && (
              <button
                type="button"
                className="quiet compact"
                disabled={btBatchBusy || Boolean(signalCollection.running)}
                onClick={() => runBatchBacktest(true)}
              >
                {btBatchBusy ? '백테스트 분석 중…' : '전체 백테스트 분석'}
              </button>
            )}
            <button
              type="button"
              className="quiet compact"
              disabled={recollecting || Boolean(signalCollection.running)}
              onClick={handleManualRecollect}
            >
              {signalCollection.running || recollecting ? '신호 계산 중…' : '지금 신호 재계산'}
            </button>
            {totalAutoEnabledCount > 0 && (
              <button
                type="button"
                className="quiet compact"
                disabled={clearingBatch}
                onClick={() => clearAutoTradeMarkets(allEnabledCodes)}
              >
                {clearingBatch ? '해제 중…' : '전체 허용 해제'}
              </button>
            )}
          </div>
        </div>
        <p className="summary">
          전체 설정 기준(<b>{globalIntervalText} MA{globalMaPeriod}</b>) 이상인 KRW 마켓입니다. <b>자동매수 허용</b>을 켠 종목만 선택한 정렬 기준(기본: 괴리율 순위)에 따라 자동 매수하며(기본값 꺼짐), 보유 코인이 신호에서 이탈하면 안전을 위해 자동 매도됩니다.
        </p>
        {signalCollection.running && (
          <div className="signal-collect-banner" role="status">
            <span className="loader" style={{ width: '14px', height: '14px' }} />
            <span>
              <b>
                {candleIntervalLabel(signalCollection.candle_interval || globalCandleInterval)} · MA
                {signalCollection.ma_period || globalMaPeriod}
              </b>{' '}
              기준으로 전체 원화 마켓 추천 신호를 실시간 계산 중입니다…
              {signalCollection.total > 0 && ` (${signalCollection.done || 0} / ${signalCollection.total} 종목 완료)`}
            </span>
          </div>
        )}
        {sellableHeldCoins.length > 0 && enabledSignalCount > 0 && (
          <div className="edge-info-banner" role="status">
            <span>
              현재 보유 중인 코인(<b>{sellableHeldCoins.map(a => a.name || a.currency).join(', ')}</b>)이 있어 기존 포지션이 매도될 때까지 신규 자동매수는 대기합니다.
            </span>
          </div>
        )}
        {autoTradeError && <p className="error">{autoTradeError}</p>}

        {signals.length > 0 && (
          <div className="rec-filter-bar" role="region" aria-label="추천 종목 정렬 및 필터">
            <div className="rec-filter-top">
              <label className="rec-sort-label">
                <span>정렬 및 매수 우선순위 기준</span>
                <select
                  aria-label="정렬 및 매수 우선순위 기준"
                  value={sortBy}
                  onChange={e => updateRecommendationPrefs(e.target.value, excludeNegativeBt)}
                >
                  {REC_SORT_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>

              <input
                type="search"
                className="rec-search-input"
                placeholder="종목명·코드 검색 (예: 비트코인, BTC)"
                aria-label="추천 종목 검색"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />

              <button
                type="button"
                className={`quiet compact rec-safety-toggle ${excludeNegativeBt ? 'active' : ''}`}
                aria-pressed={excludeNegativeBt}
                onClick={() => updateRecommendationPrefs(sortBy, !excludeNegativeBt)}
                title="켜면 백테스트 수익률이 음수(< 0%)인 종목은 자동매수 허용이 켜져 있어도 실제 자동 매수 대상에서 차단합니다."
              >
                {excludeNegativeBt ? '🛡️ 마이너스 수익률 자동매수 차단 켜짐' : '마이너스 수익률 자동매수 차단'}
              </button>
            </div>

            <div className="rec-filter-chips-row">
              <div className="rec-chip-group" role="group" aria-label="백테스트 조건 필터">
                <button
                  type="button"
                  className={`quiet compact rec-filter-chip ${hideNegativeBt ? 'active' : ''}`}
                  aria-pressed={hideNegativeBt}
                  onClick={() => setHideNegativeBt(prev => !prev)}
                >
                  수익률 마이너스 제외 (≥ 0%)
                </button>
                <button
                  type="button"
                  className={`quiet compact rec-filter-chip ${onlyPositiveExcess ? 'active' : ''}`}
                  aria-pressed={onlyPositiveExcess}
                  onClick={() => setOnlyPositiveExcess(prev => !prev)}
                >
                  시장(단순보유) 상회 (&gt; 0%p)
                </button>
                <button
                  type="button"
                  className={`quiet compact rec-filter-chip ${lowMddOnly ? 'active' : ''}`}
                  aria-pressed={lowMddOnly}
                  onClick={() => setLowMddOnly(prev => !prev)}
                >
                  안정형 (MDD ≤ 20%)
                </button>
                <button
                  type="button"
                  className={`quiet compact rec-filter-chip ${onlyAutoEnabled ? 'active' : ''}`}
                  aria-pressed={onlyAutoEnabled}
                  onClick={() => setOnlyAutoEnabled(prev => !prev)}
                >
                  자동매수 켜짐만
                </button>
                {hasActiveFilter && (
                  <button
                    type="button"
                    className="quiet compact rec-filter-reset"
                    onClick={resetFilters}
                  >
                    필터 초기화
                  </button>
                )}
              </div>
            </div>

            <div className="rec-smart-batch-row">
              <small className="rec-filter-summary">
                표시 종목 <b>{filteredSignals.length}</b> / {signals.length}개
                {negativeBtCount > 0 ? ` · 마이너스 수익률 ${negativeBtCount}종목` : ''}
              </small>
              <div className="rec-smart-actions">
                <button
                  type="button"
                  className="quiet compact rec-batch-btn"
                  disabled={clearingBatch || positiveFilteredCodes.length === 0}
                  onClick={() => enableAutoTradeMarkets(positiveFilteredCodes)}
                >
                  수익률 양수(+) 종목 일괄 허용 ({positiveFilteredCodes.length}개)
                </button>
                <button
                  type="button"
                  className="quiet compact rec-batch-btn"
                  disabled={clearingBatch || top5CandidateCodes.length === 0}
                  onClick={() => enableAutoTradeMarkets(top5CandidateCodes)}
                >
                  상위 TOP 5 일괄 허용
                </button>
                {negativeEnabledCodes.length > 0 && (
                  <button
                    type="button"
                    className="quiet compact rec-batch-btn warn"
                    disabled={clearingBatch}
                    onClick={() => clearAutoTradeMarkets(negativeEnabledCodes)}
                  >
                    마이너스 수익률 허용 종목 해제 ({negativeEnabledCodes.length}개)
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="recommendations">
          {filteredSignals.length ? (
            filteredSignals.map(r => {
              const p = computeSpreadPct(r);
              const code = r.code || r.market;
              const autoEnabled = isMarketAutoEnabled(r);
              const priorityRank = enabledRankByCode[code];
              const isNegBt = r.bt_return_pct != null && Number(r.bt_return_pct) < 0;
              const isBlockedNeg = Boolean(blockedNegativeByCode[code]) || (excludeNegativeBt && isNegBt);
              const itemIntervalText = candleIntervalLabel(r.candle_interval || globalCandleInterval);
              return (
                <article
                  className={`card ${autoEnabled ? 'auto-enabled' : ''} ${isNegBt ? 'bt-negative' : ''}`}
                  key={code}
                >
                  <div className="rec-card-head">
                    <small className="rec-card-meta">
                      <span>{code} · {itemIntervalText} MA{r.ma_period || globalMaPeriod}</span>
                      {autoEnabled && priorityRank && (
                        <span className="rec-priority-badge">매수 {priorityRank}순위</span>
                      )}
                      {autoEnabled && isNegBt && (
                        isBlockedNeg ? (
                          <span className="rec-dropped-badge">자동매수 차단 (수익률 음수)</span>
                        ) : (
                          <span className="rec-dropped-badge">⚠️ 백테스트 마이너스</span>
                        )
                      )}
                    </small>
                    <div className="rec-card-actions">
                      <button
                        type="button"
                        className={`quiet compact rec-auto-btn ${autoEnabled ? 'active' : ''}`}
                        aria-pressed={autoEnabled}
                        disabled={Boolean(togglingMarkets[code]) || clearingBatch}
                        onClick={() => toggleMarketAutoTrade(r)}
                      >
                        {autoEnabled ? '자동매수 켜짐' : '자동매수 허용'}
                      </button>
                      <button
                        type="button"
                        className="quiet compact rec-backtest-btn"
                        onClick={() => runItemBacktest(r)}
                      >
                        백테스트
                      </button>
                    </div>
                  </div>
                  <h3>{r.name || code}</h3>
                  <strong>{money(r.temp_price)}</strong>
                  <p>
                    {itemIntervalText} 평균 {money(r.setting_price)} · 괴리율 {p != null && Number.isFinite(p) ? p.toFixed(2) : '—'}%
                  </p>
                  <div className="rec-bt-strip">
                    {r.bt_return_pct != null ? (
                      <>
                        <span className={`rec-bt-primary ${Number(r.bt_return_pct) >= 0 ? 'positive' : 'negative'}`}>
                          백테스트 {Number(r.bt_return_pct) > 0 ? '+' : ''}{Number(r.bt_return_pct).toFixed(2)}%
                        </span>
                        {r.bt_excess_pct != null && (
                          <span className="rec-bt-pill">
                            초과 {Number(r.bt_excess_pct) > 0 ? '+' : ''}{Number(r.bt_excess_pct).toFixed(1)}%p
                          </span>
                        )}
                        {r.bt_mdd_pct != null && (
                          <span className="rec-bt-pill">
                            MDD {Number(r.bt_mdd_pct).toFixed(1)}%
                          </span>
                        )}
                        {r.bt_win_rate_pct != null && (
                          <span className="rec-bt-pill">
                            승률 {Number(r.bt_win_rate_pct).toFixed(0)}% ({r.bt_trade_count ?? 0}회)
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="rec-bt-uncalc">
                        {btBatchBusy ? '백테스트 계산 중…' : '백테스트 미계산'}
                      </span>
                    )}
                  </div>
                </article>
              );
            })
          ) : signals.length > 0 ? (
            <div className="empty">
              <b>선택한 필터 조건에 맞는 추천 종목이 없습니다.</b>
              <button type="button" className="empty-action-btn" onClick={resetFilters}>
                필터 초기화
              </button>
            </div>
          ) : (
            <p className="empty">
              {signalCollection.running
                ? `${globalIntervalText} MA${globalMaPeriod} 기준으로 추천 신호를 계산하고 있습니다…`
                : '현재 매수 신호가 없습니다.'}
            </p>
          )}
        </div>

        {/* Edge Case: Auto-trade enabled markets that dropped out of active recommendations */}
        {inactiveAutoItems.length > 0 && (
          <div className="inactive-auto-panel" role="region" aria-label="신호 이탈 자동매수 허용 종목">
            <div className="inactive-auto-head">
              <div>
                <strong>신호 이탈 · 대기 중인 자동매수 종목 ({inactiveAutoItems.length}개)</strong>
                <p>
                  자동매수 허용으로 체크해 두었으나 현재 이동평균선({globalIntervalText} MA{globalMaPeriod}) 아래로 내려가 추천에서 제외된 종목입니다. 현재는 매수하지 않으며, 다시 이동평균선 위로 진입하면 자동 매수됩니다. 재진입 매수를 원치 않으면 해제해 주세요.
                </p>
              </div>
              <button
                type="button"
                className="quiet compact"
                disabled={clearingBatch}
                onClick={() => clearAutoTradeMarkets(inactiveAutoItems.map(i => i.code || i.market))}
              >
                {clearingBatch ? '해제 중…' : '신호 이탈 종목 모두 해제'}
              </button>
            </div>
            <div className="inactive-auto-grid">
              {inactiveAutoItems.map(item => {
                const code = item.code || item.market;
                const itemIntervalText = candleIntervalLabel(item.candle_interval || globalCandleInterval);
                return (
                  <article className="card inactive-auto-card" key={code}>
                    <div className="rec-card-head">
                      <small className="rec-card-meta">
                        <span>{code} · {itemIntervalText} MA{item.ma_period || globalMaPeriod}</span>
                        <span className="rec-dropped-badge">신호 이탈 · 매수 대기</span>
                      </small>
                      <div className="rec-card-actions">
                        <button
                          type="button"
                          className="quiet compact rec-auto-btn active"
                          disabled={Boolean(togglingMarkets[code]) || clearingBatch}
                          onClick={() => toggleMarketAutoTrade(item, false)}
                        >
                          자동매수 해제
                        </button>
                        <button
                          type="button"
                          className="quiet compact rec-backtest-btn"
                          onClick={() => runItemBacktest(item)}
                        >
                          백테스트
                        </button>
                      </div>
                    </div>
                    <h3>{item.name || code}</h3>
                    {item.temp_price != null ? (
                      <p style={{ margin: '4px 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                        마지막 확인가 {money(item.temp_price)}
                        {item.setting_price != null ? ` · ${itemIntervalText} 평균 ${money(item.setting_price)}` : ''}
                      </p>
                    ) : (
                      <p style={{ margin: '4px 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                        현재 이동평균 매수 신호 목록 외 종목
                      </p>
                    )}
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* 3. Account Assets Table with Strategy Status & Emergency Sell */}
      <section>
        <h2>계좌 자산</h2>
        {sellMsg && <p className="error">{sellMsg}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>자산</th>
                <th>보유량</th>
                <th>평가액</th>
                <th>수익률</th>
                <th>전략 상태</th>
                <th>긴급 주문</th>
              </tr>
            </thead>
            <tbody>
              {assets.map(r => {
                const isKRW = r.currency === 'KRW';
                const marketCode = `KRW-${r.currency}`;
                const hasBuySignal = signals.some(s => (s.code || s.market) === marketCode);
                const quantity = Number(r.quantity || r.balance || 0);
                const unsellable = r.unsellable_reason;
                const assetAutoEnabled = !isKRW && isMarketAutoEnabled({ code: marketCode, auto_trade: r.auto_trade });
                return (
                  <tr key={r.currency}>
                    <td data-label="자산">{r.name || r.currency}</td>
                    <td data-label="보유량">{quantity.toLocaleString('ko-KR', { maximumFractionDigits: 8 })}</td>
                    <td data-label="평가액">{money(r.valuation)}</td>
                    <td data-label="수익률" className={r.profit_rate > 0 ? 'price-up' : r.profit_rate < 0 ? 'price-down' : ''}>
                      {r.profit_rate == null ? '—' : `${Number(r.profit_rate).toFixed(2)}%`}
                    </td>
                    <td data-label="전략 상태">
                      {isKRW ? (
                        <span className="status-pill off">현금</span>
                      ) : unsellable === 'dust' ? (
                        <span className="status-pill off" title="업비트 최소 주문금액(5,000원) 미만 소액 잔고로 자동매매 대상에서 제외됩니다.">
                          소액 잔고 (매매 제외)
                        </span>
                      ) : unsellable === 'unsupported' ? (
                        <span className="status-pill off" title="원화 마켓 거래지원이 종료된 자산입니다.">
                          거래지원 종료
                        </span>
                      ) : (
                        <div className="asset-strategy-cell">
                          {hasBuySignal ? (
                            <span className="badge" style={{ color: 'var(--state-success, #45b596)' }}>
                              HOLD
                            </span>
                          ) : (
                            <span className="badge failed" style={{ color: 'var(--price-up, #e06c75)' }}>
                              매도 신호
                            </span>
                          )}
                          <button
                            type="button"
                            className={`quiet compact rec-auto-btn ${assetAutoEnabled ? 'active' : ''}`}
                            aria-pressed={assetAutoEnabled}
                            disabled={Boolean(togglingMarkets[marketCode]) || clearingBatch}
                            onClick={() => toggleMarketAutoTrade({ code: marketCode, auto_trade: assetAutoEnabled })}
                            title="이 종목의 추후 자동매수 허용 여부를 전환합니다 (보유 코인의 신호 이탈 시 자동매도는 항상 작동)"
                          >
                            {assetAutoEnabled ? '자동매수 켜짐' : '자동매수 꺼짐'}
                          </button>
                        </div>
                      )}
                    </td>
                    <td data-label="긴급 주문">
                      {!isKRW ? (
                        <button
                          type="button"
                          className="danger"
                          style={{ padding: '4px 8px', fontSize: 'var(--text-xs)' }}
                          disabled={selling || quantity <= 0 || Boolean(unsellable)}
                          title={unsellable === 'dust' ? '최소 주문금액(5,000원) 미만 소액 잔고는 시장가 매도가 불가합니다.' : ''}
                          onClick={() => {
                            setSellMsg('');
                            setTargetSellAsset(r);
                          }}
                        >
                          {unsellable === 'dust' ? '소액 매도불가' : '긴급 매도'}
                        </button>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 4. Recent Orders with Korean Status & Order Details */}
      <section>
        <h2>최근 주문</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>시각</th>
                <th>마켓</th>
                <th>구분</th>
                <th>상태</th>
                <th>주문 가격</th>
                <th>주문 수량</th>
                <th>체결 수량</th>
              </tr>
            </thead>
            <tbody>
              {(data.recent_orders || []).length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-tertiary)' }}>
                    최근 주문 내역이 없습니다.
                  </td>
                </tr>
              ) : (
                data.recent_orders.map((r, i) => {
                  const stateLabel = displayOrderStatus(r);
                  const isMarketBuy = r.side === 'bid' && r.ord_type === 'price';
                  const isMarketSell = r.side === 'ask' && r.ord_type === 'market';
                  const priceText = isMarketSell
                    ? '시장가'
                    : isMarketBuy
                    ? `시장가 (${money(r.price)})`
                    : r.price
                    ? money(r.price)
                    : '—';
                  const volText = isMarketBuy
                    ? '—'
                    : r.volume
                    ? Number(r.volume).toLocaleString('ko-KR', { maximumFractionDigits: 8 })
                    : '—';
                  const execVolText = r.executed_volume
                    ? Number(r.executed_volume).toLocaleString('ko-KR', { maximumFractionDigits: 8 })
                    : '—';
                  return (
                    <tr key={r.uuid || i}>
                      <td data-label="시각">{date(r.created_at)}</td>
                      <td data-label="마켓">{r.market}</td>
                      <td data-label="구분" className={r.side === 'bid' ? 'price-up' : 'price-down'}>
                        {r.side === 'bid' ? '매수' : '매도'}
                      </td>
                      <td data-label="상태">
                        <span className={`order-state ${r.state || ''}`}>
                          {stateLabel}
                        </span>
                      </td>
                      <td data-label="주문 가격">{priceText}</td>
                      <td data-label="주문 수량">{volText}</td>
                      <td data-label="체결 수량">{execVolText}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Emergency Market Sell Confirmation Modal */}
      {targetSellAsset && (
        <div className="safe-sell-overlay" role="dialog" aria-modal="true">
          <div className="safe-sell-modal">
            <div className="safe-sell-header">
              <div className="safe-sell-title-wrap">
                <span className="safe-sell-shield-badge">EMERGENCY SELL</span>
                <h3>{targetSellAsset.name || targetSellAsset.currency} 긴급 시장가 매도</h3>
              </div>
              <button
                type="button"
                className="safe-sell-close-btn"
                disabled={selling}
                onClick={() => setTargetSellAsset(null)}
              >
                ✕
              </button>
            </div>
            <dl className="safe-sell-details">
              <div>
                <dt>종목 마켓</dt>
                <dd>KRW-{targetSellAsset.currency}</dd>
              </div>
              <div>
                <dt>매도 수량</dt>
                <dd>
                  {Number(targetSellAsset.balance || targetSellAsset.quantity || 0).toLocaleString('ko-KR', {
                    maximumFractionDigits: 8,
                  })}{' '}
                  {targetSellAsset.currency}
                </dd>
              </div>
              <div>
                <dt>예상 평가액</dt>
                <dd className="highlight-krw">{money(targetSellAsset.valuation)}</dd>
              </div>
            </dl>
            <div className="safe-sell-warning-box">
              <b>⚠️ 실제 주문 실행 경고</b>
              <p>실제 업비트 계좌에서 시장가 매도가 즉시 실행됩니다. 의도치 않은 재매수를 막기 위해 해당 종목의 <b>자동매수 허용</b>도 함께 해제됩니다. 계속하시겠습니까?</p>
            </div>
            {sellMsg && <p className="error" style={{ margin: '8px 0 0' }}>{sellMsg}</p>}
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
              <button
                type="button"
                className="quiet"
                disabled={selling}
                onClick={() => setTargetSellAsset(null)}
              >
                취소
              </button>
              <button
                type="button"
                className="danger"
                disabled={selling}
                onClick={handleEmergencySell}
              >
                {selling ? '매도 실행 중…' : '전량 시장가 매도 확인'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Per-Recommendation Backtest Result Modal */}
      {btTarget && (
        <div
          className="safe-sell-overlay backtest-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={`${btTarget.name} 백테스트 결과`}
        >
          <div className="safe-sell-modal backtest-modal">
            <div className="safe-sell-header">
              <div className="safe-sell-title-wrap">
                <span className="safe-sell-shield-badge">BACKTEST SIMULATION</span>
                <h3>
                  {btTarget.name} ({btTarget.code}) 백테스트
                </h3>
                {btUsedParams && (
                  <small style={{ color: 'var(--text-secondary)' }}>
                    기준 {candleIntervalLabel(btUsedParams.candle_interval)} MA{btUsedParams.ma_period} · 기간 {btUsedParams.days}봉 · 초기 자금{' '}
                    {money(btUsedParams.initial_capital)} · 수수료 {btUsedParams.fee_bps}bps · 슬리피지{' '}
                    {btUsedParams.slippage_bps}bps
                  </small>
                )}
              </div>
              <button
                type="button"
                className="safe-sell-close-btn"
                onClick={() => setBtTarget(null)}
              >
                ✕
              </button>
            </div>

            {btBusy && (
              <div className="loading-row" style={{ padding: '28px 0' }}>
                <span className="loader" />
                <span>{candleIntervalLabel(btUsedParams?.candle_interval)} 시세를 불러와 백테스트 수익률을 계산 중입니다…</span>
              </div>
            )}

            {btError && (
              <div>
                <p className="error" style={{ marginBottom: '10px' }}>{btError}</p>
                <button
                  type="button"
                  className="quiet"
                  onClick={() => runItemBacktest({ code: btTarget.code, name: btTarget.name })}
                >
                  다시 시도
                </button>
              </div>
            )}

            {btResult && (
              <div className="backtest-modal-body">
                <section className="metric-grid">
                  <article className="card">
                    <small>최종 평가액</small>
                    <strong>{money(btResult.final_equity)}</strong>
                  </article>
                  <article className="card">
                    <small>전략 수익률</small>
                    <strong className={btResult.return_pct > 0 ? 'price-up' : btResult.return_pct < 0 ? 'price-down' : ''}>
                      {btResult.return_pct > 0 ? '+' : ''}
                      {Number(btResult.return_pct).toFixed(2)}%
                    </strong>
                  </article>
                  <article className="card">
                    <small>단순 보유 수익률</small>
                    <strong className={btResult.benchmark_return_pct > 0 ? 'price-up' : btResult.benchmark_return_pct < 0 ? 'price-down' : ''}>
                      {btResult.benchmark_return_pct > 0 ? '+' : ''}
                      {Number(btResult.benchmark_return_pct).toFixed(2)}%
                    </strong>
                  </article>
                  <article className="card">
                    <small>초과 수익률</small>
                    <strong className={btResult.excess_return_pct > 0 ? 'price-up' : btResult.excess_return_pct < 0 ? 'price-down' : ''}>
                      {btResult.excess_return_pct > 0 ? '+' : ''}
                      {Number(btResult.excess_return_pct).toFixed(2)}%p
                    </strong>
                  </article>
                  <article className="card">
                    <small>최대 낙폭</small>
                    <strong className="price-down">{Number(btResult.max_drawdown_pct).toFixed(2)}%</strong>
                  </article>
                  <article className="card">
                    <small>완료 거래</small>
                    <strong>{btResult.trade_count}회</strong>
                  </article>
                  <article className="card">
                    <small>매매 승률</small>
                    <strong>
                      {btResult.win_rate_pct != null ? `${Number(btResult.win_rate_pct).toFixed(1)}%` : '—'}
                    </strong>
                  </article>
                </section>

                <BacktestEquityCurve
                  curve={btResult.curve}
                  initialCapital={btResult.initial_capital || btUsedParams?.initial_capital || 1000000}
                />

                <section style={{ marginTop: '14px' }}>
                  <h4 style={{ margin: '0 0 8px' }}>
                    거래 내역 ({btResult.market} · {candleIntervalLabel(btResult.candle_interval || btUsedParams?.candle_interval)} {btResult.days}봉 · 기준 MA{btResult.ma_period})
                  </h4>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>일자</th>
                          <th>구분</th>
                          <th>체결가</th>
                          <th>평가금액</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(btResult.trades || []).length === 0 ? (
                          <tr>
                            <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-tertiary)' }}>
                              기간 내 발생한 거래가 없습니다.
                            </td>
                          </tr>
                        ) : (
                          btResult.trades.map((r, i) => (
                            <tr key={`${r.date}-${i}`}>
                              <td data-label="일자">{r.date}</td>
                              <td data-label="구분" className={r.side === 'BUY' ? 'price-up' : 'price-down'}>
                                {r.side === 'BUY' ? '매수' : '매도'}
                                {r.forced ? ' (종료 청산)' : ''}
                              </td>
                              <td data-label="체결가">{money(r.price)}</td>
                              <td data-label="평가금액">{money(r.value)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
              <button type="button" className="quiet" onClick={() => setBtTarget(null)}>
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function StrategySettings({ dashboard, onChanged }) {
  const initCfg = (dashboard && dashboard.strategy_settings) || {};
  const signalCollection = (dashboard && dashboard.signal_collection) || {};
  const [form, setForm] = useState({
    candle_interval: initCfg.candle_interval || 'days',
    ma_period: Number(initCfg.ma_period || 40),
    days: Number(initCfg.days || 180),
    initial_capital: Number(initCfg.initial_capital || 1000000),
    fee_bps: Number(initCfg.fee_bps ?? 5),
    slippage_bps: Number(initCfg.slippage_bps ?? 10),
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    api('/strategies')
      .then(x => {
        if (!x) return;
        setForm(prev => ({
          candle_interval: x.candle_interval || prev.candle_interval || 'days',
          ma_period: Number(x.ma_period || x.default_ma_period || prev.ma_period || 40),
          days: Number(x.days || prev.days || 180),
          initial_capital: Number(x.initial_capital || prev.initial_capital || 1000000),
          fee_bps: Number(x.fee_bps ?? prev.fee_bps ?? 5),
          slippage_bps: Number(x.slippage_bps ?? prev.slippage_bps ?? 10),
        }));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!signalCollection.running || !onChanged) return undefined;
    const timer = setInterval(() => {
      onChanged();
    }, 2000);
    return () => clearInterval(timer);
  }, [signalCollection.running, onChanged]);

  function handleChange(e) {
    const { name, value } = e.target;
    if (name === 'candle_interval') {
      setForm(prev => ({ ...prev, candle_interval: value }));
      return;
    }
    const num = Number(value);
    if (name === 'ma_period') {
      setForm(prev => ({
        ...prev,
        ma_period: num,
        days: Math.max(prev.days, Math.min(200, Math.max(60, num + 2))),
      }));
    } else {
      setForm(prev => ({ ...prev, [name]: num }));
    }
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setMessage('');
    try {
      const safeDays = Math.min(200, Math.max(60, form.ma_period + 2, Number(form.days || 180)));
      const res = await api('/strategies', {
        method: 'PUT',
        body: JSON.stringify({
          market: '__GLOBAL__',
          candle_interval: form.candle_interval,
          ma_period: Number(form.ma_period),
          days: safeDays,
          initial_capital: Number(form.initial_capital),
          fee_bps: Number(form.fee_bps),
          slippage_bps: Number(form.slippage_bps),
        }),
      });
      const intervalName = candleIntervalLabel(form.candle_interval);
      setMessage(
        res && res.recollect_started
          ? `전체 공통 설정(${intervalName} MA${form.ma_period} · ${safeDays}봉 백테스트)을 저장하고 추천 신호 재계산을 시작했습니다.`
          : `전체 공통 설정(${intervalName} MA${form.ma_period} · ${safeDays}봉 백테스트)을 저장했습니다.`
      );
      if (onChanged) await onChanged();
    } catch (x) {
      setMessage(x.message);
    } finally {
      setBusy(false);
    }
  }

  const selectedIntervalLabel = candleIntervalLabel(form.candle_interval);

  return (
    <section className="card">
      <h2>전체 전략 및 백테스트 설정</h2>
      <p className="info-note">
        모든 KRW 마켓 신호 수집과 추천 종목 백테스트에 공통으로 적용되는 전체 설정입니다. 캔들 단위(30분봉·1시간봉·4시간봉·일봉·주봉)나 기준 봉 수를 저장하면 즉시 추천 신호를 재계산하여 모니터링 탭에 표시합니다.
      </p>
      {signalCollection.running && (
        <div className="signal-collect-banner" role="status" style={{ marginBottom: '12px' }}>
          <span className="loader" style={{ width: '14px', height: '14px' }} />
          <span>
            <b>
              {candleIntervalLabel(signalCollection.candle_interval || form.candle_interval)} · MA
              {signalCollection.ma_period || form.ma_period}
            </b>{' '}
            기준으로 추천 종목을 계산하고 있습니다…
            {signalCollection.total > 0 && ` (${signalCollection.done || 0} / ${signalCollection.total} 종목)`}
          </span>
        </div>
      )}
      <form className="form" onSubmit={save}>
        <div className="candle-interval-field">
          <span className="field-label">캔들 단위 (봉 기준)</span>
          <div className="candle-interval-group" role="radiogroup" aria-label="캔들 단위 선택">
            {CANDLE_INTERVAL_OPTIONS.map(opt => {
              const active = form.candle_interval === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  className={`quiet compact candle-interval-btn ${active ? 'active' : ''}`}
                  onClick={() => setForm(prev => ({ ...prev, candle_interval: opt.value }))}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <small>선택한 캔들({selectedIntervalLabel})을 기준으로 이동평균 매수/매도 신호와 백테스트를 계산합니다.</small>
        </div>
        <label>
          기준 봉 수 (MA · 기준 일봉 수 (MA))
          <input
            name="ma_period"
            type="number"
            min="2"
            max="199"
            value={form.ma_period}
            onChange={handleChange}
            required
          />
          <small>직전 완료 {selectedIntervalLabel} 기준 이동평균 봉 수입니다 (기본 40봉, 2~199).</small>
        </label>
        <label>
          백테스트 기간(봉 · 백테스트 기간(일))
          <input
            name="days"
            type="number"
            min={Math.max(60, form.ma_period + 2)}
            max="200"
            value={form.days}
            onChange={handleChange}
            required
          />
          <small>기준 봉 수보다 최소 2봉 길어야 하며 최대 200봉({selectedIntervalLabel} 기준)입니다.</small>
        </label>
        <label>
          백테스트 초기 자금(원)
          <input
            name="initial_capital"
            type="number"
            min="1"
            value={form.initial_capital}
            onChange={handleChange}
            required
          />
        </label>
        <label>
          편도 수수료(bps)
          <input
            name="fee_bps"
            type="number"
            min="0"
            max="1000"
            step="0.1"
            value={form.fee_bps}
            onChange={handleChange}
          />
        </label>
        <label>
          편도 슬리피지(bps)
          <input
            name="slippage_bps"
            type="number"
            min="0"
            max="1000"
            step="0.1"
            value={form.slippage_bps}
            onChange={handleChange}
          />
        </label>
        <button className="primary" disabled={busy}>
          {busy ? '저장 및 재계산 시작 중…' : '전체 설정 저장'}
        </button>
      </form>
      {message && <p role="status">{message}</p>}
    </section>
  );
}

export function Settings({ dashboard, onChanged }) {
  const [a, setA] = useState('');
  const [s, setS] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [publicIp, setPublicIp] = useState('확인 중');
  const [ipCopied, setIpCopied] = useState(false);
  const [showAutoConfirm, setShowAutoConfirm] = useState(false);
  const cfg = (dashboard && dashboard.strategy_settings) || {};
  const candleInterval = cfg.candle_interval || 'days';
  const intervalText = candleIntervalLabel(candleInterval);
  const maPeriod = Number(cfg.ma_period || 40);
  const btDays = Number(cfg.days || 180);
  const btCap = Number(cfg.initial_capital || 1000000);
  const btFee = Number(cfg.fee_bps ?? 5);
  const btSlip = Number(cfg.slippage_bps ?? 10);

  useEffect(() => {
    api('/system/public-ip')
      .then(x => setPublicIp(x.public_ip))
      .catch(() => setPublicIp('확인 실패'));
  }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api('/upbit/key', {
        method: 'PUT',
        body: JSON.stringify({ access_key: a, secret_key: s }),
      });
      setA('');
      setS('');
      setMsg('키를 암호화해 저장했습니다.');
      if (onChanged) await onChanged();
    } catch (x) {
      setMsg(x.message);
    } finally {
      setBusy(false);
    }
  }

  function handleToggleClick() {
    setMsg('');
    if (!dashboard.auto_on) {
      setShowAutoConfirm(true);
    } else {
      executeToggle(false);
    }
  }

  async function executeToggle(turnOn) {
    setBusy(true);
    setMsg('');
    try {
      await api('/upbit/auto', {
        method: 'PUT',
        body: JSON.stringify({ auto_on: turnOn }),
      });
      setShowAutoConfirm(false);
      if (onChanged) await onChanged();
    } catch (x) {
      setMsg(x.message);
    } finally {
      setBusy(false);
    }
  }

  function copyPublicIp() {
    if (publicIp && publicIp !== '확인 중' && publicIp !== '확인 실패' && navigator.clipboard) {
      navigator.clipboard.writeText(publicIp);
      setIpCopied(true);
      setTimeout(() => setIpCopied(false), 2000);
    }
  }

  return (
    <>
      <StrategySettings dashboard={dashboard} onChanged={onChanged} />

      <section className="card">
        <h2>전략 동작</h2>
        <dl>
          <dt>거래소</dt>
          <dd>Upbit KRW 마켓</dd>
          <dt>전체 기준 전략</dt>
          <dd>
            {candleInterval === 'days'
              ? `${maPeriod}일 단순 이동평균(일봉 MA${maPeriod})`
              : `${intervalText} ${maPeriod}봉 단순 이동평균(${intervalText} MA${maPeriod})`}
          </dd>
          <dt>백테스트 기준</dt>
          <dd>
            {intervalText} {btDays}봉 · 초기 자금 {money(btCap)} · 수수료 {btFee}bps · 슬리피지 {btSlip}bps
          </dd>
          <dt>매수</dt>
          <dd>현재가 ≥ 전체 설정 완료 {intervalText} 평균 (자동매수 허용 종목만)</dd>
          <dt>매도</dt>
          <dd>현재가 &lt; 전체 설정 {intervalText} 이동평균</dd>
          <dt>판단 주기</dt>
          <dd>신호 5분(설정 변경 시 즉시) · 주문 30초</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Upbit API 연결</h2>
        <p>Upbit 허용 IP에 아래 주소를 먼저 등록하세요.</p>
        <p style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <b>
            이 서버의 공인 출구 IP: <code>{publicIp}</code>
          </b>
          <button
            type="button"
            className="quiet"
            style={{ padding: '3px 8px', fontSize: 'var(--text-xs)' }}
            disabled={!publicIp || publicIp === '확인 중' || publicIp === '확인 실패'}
            onClick={copyPublicIp}
          >
            {ipCopied ? '복사 완료!' : '공인 IP 복사'}
          </button>
        </p>
        <p className="info-note">
          가정용 회선, VPN, 프록시 또는 재시작되는 클라우드 IP는 바뀔 수 있습니다. 자동매매 서버에는 고정 공인 IP를 사용하고 IP 변경 시 Upbit 허용 목록도 갱신하세요.
        </p>
        <p>
          키 상태: <b>{dashboard.key_registered ? '등록됨' : '미등록'}</b>
        </p>
        <form className="form" onSubmit={save}>
          <label>
            Access Key
            <input value={a} onChange={e => setA(e.target.value)} required />
          </label>
          <label>
            Secret Key
            <input type="password" value={s} onChange={e => setS(e.target.value)} required />
          </label>
          <button className="primary" disabled={busy}>
            키 저장
          </button>
        </form>
      </section>

      <section className="card">
        <h2>실제 자동매매</h2>
        <p>
          {dashboard.auto_on ? '실제 주문이 활성화되어 있습니다.' : '현재 주문은 실행되지 않습니다.'}
        </p>
        <button
          type="button"
          className={dashboard.auto_on ? 'danger' : 'primary'}
          disabled={busy || !dashboard.key_registered}
          onClick={handleToggleClick}
        >
          {dashboard.auto_on ? '자동매매 끄기' : '자동매매 켜기'}
        </button>
        {msg && <p>{msg}</p>}
      </section>

      {/* Auto-Trade Activation Confirmation Modal */}
      {showAutoConfirm && (
        <div className="safe-sell-overlay" role="dialog" aria-modal="true">
          <div className="safe-sell-modal">
            <div className="safe-sell-header">
              <div className="safe-sell-title-wrap">
                <span className="safe-sell-shield-badge">SAFETY CONFIRMATION</span>
                <h3>자동매매 활성화 확인</h3>
              </div>
              <button
                type="button"
                className="safe-sell-close-btn"
                disabled={busy}
                onClick={() => setShowAutoConfirm(false)}
              >
                ✕
              </button>
            </div>
            <div className="safe-sell-warning-box">
              <b>⚠️ 실제 주문 실행 경고</b>
              <p>실제 업비트 계좌에서 자동 주문이 실행됩니다. 활성화하시겠습니까?</p>
            </div>
            {msg && <p className="error" style={{ margin: '8px 0 0' }}>{msg}</p>}
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
              <button
                type="button"
                className="quiet"
                disabled={busy}
                onClick={() => setShowAutoConfirm(false)}
              >
                취소
              </button>
              <button
                type="button"
                className="primary"
                disabled={busy}
                onClick={() => executeToggle(true)}
              >
                {busy ? '활성화 중…' : '활성화'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function App() {
  const [user, setUser] = useState(null);
  const [dash, setDash] = useState(null);
  const [tab, setTab] = useState('monitor');
  const [error, setError] = useState('');
  const [showInstallModal, setShowInstallModal] = useState(false);
  const pwa = usePwaInstall();

  const loadUser = useCallback(
    () =>
      api('/auth/me')
        .then(setUser)
        .catch(() => setUser(null)),
    []
  );

  const load = useCallback(async () => {
    try {
      setError('');
      setDash(await api('/dashboard'));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!user) return;
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [user, load]);

  if (!user) return <Login onLogin={loadUser} />;
  if (!dash)
    return (
      <main className="content">
        <p>{error || '데이터를 불러오는 중입니다.'}</p>
        <button type="button" onClick={load}>
          다시 시도
        </button>
      </main>
    );

  const nav = [
    ['monitor', '모니터링'],
    ['settings', '설정'],
    ['guide', '가이드'],
  ];

  return (
    <div className="layout">
      <header className="topbar">
        <div className="topbar-brand">
          <BrandLogo size={42} className="topbar-brand-logo" />
          <div>
            <small className="eyebrow">UPBIT ONLY</small>
            <h1>MA40 Auto Trader</h1>
          </div>
        </div>
        <div className="topbar-actions">
          {!pwa.isInstalled && (
            <button
              type="button"
              className="quiet pwa-topbar-install-btn"
              onClick={() => setShowInstallModal(true)}
            >
              📲 앱 설치
            </button>
          )}
          <button
            type="button"
            className="quiet"
            onClick={async () => {
              await api('/auth/logout', { method: 'POST' });
              setUser(null);
            }}
          >
            로그아웃
          </button>
        </div>
      </header>
      <nav className="tabs">
        {nav.map(([k, l]) => (
          <button
            key={k}
            type="button"
            className={tab === k ? 'active' : ''}
            onClick={() => setTab(k)}
          >
            {l}
          </button>
        ))}
      </nav>
      <main className="content">
        {error && <p className="error">{error}</p>}
        {tab === 'monitor' && <Monitor data={dash} refresh={load} />}
        {tab === 'settings' && <Settings dashboard={dash} onChanged={load} />}
        {tab === 'guide' && <UsageGuide />}
      </main>
      <AppInstallModal open={showInstallModal} onClose={() => setShowInstallModal(false)} pwa={pwa} />
    </div>
  );
}

const rootElement = typeof document !== 'undefined' ? document.getElementById('root') : null;
if (rootElement) {
  createRoot(rootElement).render(<App />);
}
