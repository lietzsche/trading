import {afterEach, describe, expect, it, vi} from 'vitest';
import {api, ApiError, createRequestGate, errorMessage, orderStatus} from './api';

afterEach(() => vi.unstubAllGlobals());

describe('API errors', () => {
  it('renders FastAPI field validation errors without stringifying objects', () => {
    expect(errorMessage([{loc: ['body', 'expected_high_percentage'], type: 'greater_than', ctx: {gt: 0}, msg: 'Input should be greater than 0'}], 422))
      .toBe('목표 상승률: 0보다 큰 값을 입력해 주세요.');
  });
  it('uses a safe fallback for an unexpected error body', () => {
    expect(errorMessage({internal: 'not a public message'}, 502)).toContain('502');
    expect(errorMessage(null, 401)).toContain('다시 로그인');
  });
  it('preserves an HTTP status for session expiry handling', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false, status: 401, json: async () => ({})}));
    await expect(api('/auth/me')).rejects.toMatchObject({name: 'ApiError', status: 401});
  });
  it('merges request headers and handles empty responses', async () => {
    const fetch = vi.fn().mockResolvedValue({ok: true, status: 204});
    vi.stubGlobal('fetch', fetch);
    await expect(api('/auth/logout', {method: 'POST', headers: {'X-Test': 'yes'}})).resolves.toBeNull();
    expect(fetch.mock.calls[0][1].headers).toEqual({'Content-Type': 'application/json', 'X-Test': 'yes'});
  });
});

describe('latest request gate', () => {
  it('rejects stale responses after a tab switch or a newer filter request', () => {
    const gate = createRequestGate();
    const old = gate.begin(), current = gate.begin();
    expect(old.signal.aborted).toBe(true);
    expect(old.isCurrent()).toBe(false);
    expect(current.isCurrent()).toBe(true);
  });
  it('rejects responses after unmounting', () => {
    const gate = createRequestGate(), request = gate.begin();
    gate.cancel();
    expect(request.signal.aborted).toBe(true);
    expect(request.isCurrent()).toBe(false);
  });
});

describe('cancelled order labels', () => {
  it('does not describe a partially filled limit sell as fully completed', () => {
    expect(orderStatus({state: 'cancel', side: 'ask', ord_type: 'limit', executed_volume: '2'}).label).toBe('일부 체결 · 취소');
  });
  it('explains market buy remainder cancellation without claiming a complete fill', () => {
    expect(orderStatus({state: 'cancel', side: 'bid', ord_type: 'price', executed_volume: '2'}).label).toBe('체결 있음 · 잔액 취소');
  });
  it('leaves an unfilled cancellation and a completed order unchanged', () => {
    expect(orderStatus({state: 'cancel', executed_volume: '0'})).toBeNull();
    expect(orderStatus({state: 'done', executed_volume: '3'})).toBeNull();
  });
});
