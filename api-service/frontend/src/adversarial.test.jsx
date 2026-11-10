import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { displayOrderStatus, orderStatus, money, date } from './api';
import { Monitor, Settings, Login } from './main';

describe('Adversarial Frontend Edge Cases', () => {
  it('handles empty dashboard object without crashing', () => {
    expect(() => {
      renderToStaticMarkup(<Monitor data={{}} refresh={() => {}} />);
    }).not.toThrow();
  });

  it('handles missing performance object gracefully', () => {
    const dataWithoutPerf = {
      total_valuation: null,
      safety: { level: 'healthy', summary: '정상' },
      recommendations: [],
      assets: [],
      recent_orders: [],
    };
    let html;
    expect(() => {
      html = renderToStaticMarkup(<Monitor data={dataWithoutPerf} refresh={() => {}} />);
    }).not.toThrow();
    expect(html).toContain('—');
  });

  it('handles unresolved_orders as list of objects (real backend schema) when blocked', () => {
    const dataBlockedWithList = {
      total_valuation: 10000000,
      safety: {
        level: 'blocked',
        summary: '미확인 주문 대기',
        unresolved_orders: [
          { identifier: 'auto-ord-1234', market: 'KRW-BTC', created_at: '2026-11-09T14:00:00Z' },
          { identifier: 'auto-ord-5678', market: 'KRW-ETH', created_at: '2026-11-09T14:01:00Z' },
        ],
      },
      performance: null,
      recommendations: [],
      assets: [],
      recent_orders: [],
    };

    // Does it crash or render cleanly?
    let rendered;
    let error;
    try {
      rendered = renderToStaticMarkup(<Monitor data={dataBlockedWithList} refresh={() => {}} />);
    } catch (e) {
      error = e;
    }

    // Verify whether this causes a fatal React error
    if (error) {
      console.error('CRASH DETECTED on unresolved_orders list:', error.message);
    }
    expect(error).toBeUndefined();
    expect(rendered).toContain('미확인 주문 수');
  });

  it('handles malformed, extreme, and negative numbers in performance and recent orders', () => {
    const extremeData = {
      total_valuation: 999999999999999999, // 100경
      today_executed_count: -5,
      performance: {
        invested: 1e15,
        unrealized_profit: -500000000,
        unrealized_rate: -99.99,
        today_change: 0,
        today_change_rate: 0,
      },
      safety: {
        level: 'warning',
        summary: null,
        price_updated_at: 'invalid-date-string',
        unresolved_orders: 0,
      },
      recommendations: [
        { code: 'KRW-ZERO', name: '영원코인', temp_price: 0, setting_price: 0, ma_period: 0 },
        { code: 'KRW-NAN', name: '결측코인', temp_price: 'abc', setting_price: 'def', ma_period: null },
      ],
      assets: [
        { currency: 'ZERO', name: '영', balance: '0', valuation: 0, profit_rate: null },
        { currency: 'HUGE', name: '대용량', balance: '123456789.987654321', valuation: 1e12, profit_rate: 15423.89 },
        { currency: 'MALFORMED', name: '불량', balance: null, valuation: null, profit_rate: 'invalid' },
      ],
      recent_orders: [
        { uuid: null, created_at: null, market: 'KRW-TEST', side: null, ord_type: null, price: null, volume: null, executed_volume: null, state: null },
        { uuid: 'o-huge', created_at: '2026-11-09T00:00:00Z', market: 'KRW-BTC', side: 'bid', ord_type: 'price', price: '999999999999', volume: '100000', executed_volume: '100000', state: 'unknown_state' },
      ],
    };

    expect(() => {
      const html = renderToStaticMarkup(<Monitor data={extremeData} refresh={() => {}} />);
      expect(html).toBeDefined();
    }).not.toThrow();
  });
});
