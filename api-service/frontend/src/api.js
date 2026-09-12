const fieldLabels = {
  login_id: '아이디', password: '비밀번호', name: '이름', email: '이메일',
  access_key: 'Access Key', secret_key: 'Secret Key',
  expected_high_percentage: '목표 상승률', expected_low_percentage: '허용 하락률',
  highest_price_reference_days: '분석 기간', volume_check: '거래량 조건',
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function errorMessage(detail, status) {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (typeof item === 'string') return item;
      if (!item || typeof item.msg !== 'string') return '';
      const field = item.loc?.filter(part => !['body', 'query', 'path'].includes(part)).at(-1);
      const context = item.ctx || {};
      const descriptions = {
        greater_than: `${context.gt}보다 큰 값을 입력해 주세요.`,
        greater_than_equal: `${context.ge} 이상으로 입력해 주세요.`,
        less_than: `${context.lt}보다 작은 값을 입력해 주세요.`,
        less_than_equal: `${context.le} 이하로 입력해 주세요.`,
        int_parsing: '정수를 입력해 주세요.',
        int_from_float: '정수를 입력해 주세요.',
        missing: '필수 항목입니다.',
        string_too_short: `${context.min_length}자 이상 입력해 주세요.`,
        string_too_long: `${context.max_length}자 이하로 입력해 주세요.`,
      };
      return `${field ? `${fieldLabels[field] || field}: ` : ''}${descriptions[item.type] || item.msg}`;
    }).filter(Boolean);
    if (messages.length) return messages.join(' / ');
  }
  if (status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.';
  if (status === 403) return '이 작업에 대한 접근 권한이 없습니다.';
  return `요청에 실패했습니다 (${status}). 잠시 후 다시 시도해 주세요.`;
}

export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin', ...options,
    headers: {'Content-Type': 'application/json', ...options.headers},
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(errorMessage(payload.detail, response.status), response.status);
  }
  if (response.status === 204) return null;
  return response.json();
}

// Cancellation reduces unnecessary work; the identity check also protects against
// a response that finished just before abort() or a transport that ignores it.
export function createRequestGate() {
  let controller;
  return {
    begin() {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      return {signal: current.signal, isCurrent: () => controller === current && !current.signal.aborted};
    },
    cancel() {
      controller?.abort();
      controller = undefined;
    },
  };
}

export function orderStatus(row) {
  if (row.state !== 'cancel' || Number(row.executed_volume || 0) <= 0) return null;
  const marketBuy = row.side === 'bid' && row.ord_type === 'price';
  return marketBuy
    ? {label: '체결 있음 · 잔액 취소', note: '시장가 매수에서 체결되지 않은 주문 잔액이 취소되었습니다. 실제 체결 수량을 확인해 주세요.'}
    : {label: '일부 체결 · 취소', note: '일부 수량이 체결된 후 나머지 주문이 취소되었습니다.'};
}
