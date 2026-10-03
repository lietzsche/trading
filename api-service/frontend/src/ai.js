export const AI_SETTING_FIELDS = [
  ['expected_high_percentage', '목표 상승률', '%'],
  ['expected_low_percentage', '허용 하락률', '%'],
  ['highest_price_reference_days', '분석 기간', '일'],
  ['volume_check', '거래량 조건', ''],
];

export const AI_STATUS_LABELS = {PENDING: '분석 대기', RUNNING: '분석 중', COMPLETED: '분석 완료', FAILED: '분석 실패'};

export function isAnalysisRunning(status) {
  return status === 'PENDING' || status === 'RUNNING';
}

export function parseAnalysisSymbols(text, market) {
  const symbols = [...new Set(text.trim().toUpperCase().split(/[\s,]+/).filter(Boolean).map(code=>market==='stock'&&!/^\d{6}$/.test(code)&&!code.startsWith('US:')&&!code.startsWith('KRW-')?`US:${code}`:code))];
  if (symbols.length > 5) throw new Error('종목은 최대 5개까지 입력해 주세요.');
  const pattern = market === 'upbit' ? /^KRW-[A-Z0-9]+$/ : /^(?:\d{6}|US:[A-Z][A-Z0-9-]{0,14})$/;
  if (symbols.some(symbol => !pattern.test(symbol))) {
    throw new Error(market === 'upbit' ? 'Upbit 종목은 KRW-BTC처럼 원화 마켓 코드를 입력해 주세요.' : '국내는 005930처럼 6자리 코드, 미국은 AAPL 또는 US:AAPL 형식으로 입력해 주세요.');
  }
  return symbols;
}

export function settingText(key, value) {
  if (value === null || value === undefined) return '확인 불가';
  if (key === 'volume_check') return value ? '사용' : '미사용';
  const unit = AI_SETTING_FIELDS.find(([field]) => field === key)?.[2] || '';
  return `${Number(value).toLocaleString('ko-KR')}${unit}`;
}

export function percentText(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return `${Number(value).toLocaleString('ko-KR', {maximumFractionDigits: 2})}%`;
}

export function textItems(value) {
  if (typeof value === 'string') return [value];
  if (!Array.isArray(value)) return [];
  return value.map(item => typeof item === 'string' ? item : item?.message || item?.description || item?.label || '').filter(Boolean);
}

export function sameSettings(before, after) {
  return Boolean(before && after && AI_SETTING_FIELDS.every(([key]) => before[key] === after[key]));
}

export function candidateRiskLabel(settings, baseline) {
  if (!settings || !baseline) return null;
  const high = Number(settings.expected_high_percentage), low = Math.abs(Number(settings.expected_low_percentage));
  const baseHigh = Number(baseline.expected_high_percentage), baseLow = Math.abs(Number(baseline.expected_low_percentage));
  if (![high, low, baseHigh, baseLow].every(Number.isFinite)) return null;
  const wider = high > baseHigh || low > baseLow, narrower = high < baseHigh || low < baseLow;
  if (wider && !narrower) return {text: '공격적', tone: 'high'};
  if (narrower && !wider) return {text: '보수적', tone: 'low'};
  if (!wider && !narrower) return {text: '동일 폭', tone: 'mixed'};
  return {text: '변형', tone: 'mixed'};
}

export function candidateEligible(candidate) {
  return Boolean(candidate && !['current', 'baseline'].includes(candidate.id)
    && candidate.can_apply !== false && Number(candidate.validation?.trades || 0) > 0
    && Number(candidate.validation?.days || 0) >= 10);
}

export function autoApplyEligible(candidate, baseline) {
  if (!candidate || ['current', 'baseline'].includes(candidate.id) || candidate.can_apply === false) return false;
  const metrics = candidate.validation, base = baseline?.validation;
  const raw = [metrics?.days, metrics?.trades, metrics?.return_pct, metrics?.max_drawdown_pct, base?.return_pct, base?.max_drawdown_pct];
  if (raw.some(value => value == null || value === '' || !Number.isFinite(Number(value)))) return false;
  const [days, trades, returns, drawdown, baseReturn, baseDrawdown] = raw.map(Number);
  return days >= 20 && trades >= 3 && returns > baseReturn && baseDrawdown >= 0 && drawdown >= 0 && drawdown <= baseDrawdown + 2;
}
