import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { displayOrderStatus, orderStatus } from './api';
import {
  AppInstallModal,
  BacktestEquityCurve,
  BrandLogo,
  Login,
  Monitor,
  Settings,
  batchUpdateAutoTradeMarkets,
  computeEnabledRanks,
  date,
  filterRecommendations,
  money,
  sortRecommendations,
} from './main';

afterEach(() => vi.unstubAllGlobals());

describe('format helpers', () => {
  it('formats money and date properly', () => {
    expect(money(1234567)).toBe('₩1,234,567');
    expect(money(0)).toBe('₩0');
    expect(money(null)).toBe('₩0');
    expect(date('2026-11-09T14:30:00Z')).toBe('2026-11-09 14:30:00');
    expect(date(null)).toBe('—');
  });
});

describe('Monitor component', () => {
  const sampleDashboard = {
    total_valuation: 15000000,
    today_executed_count: 3,
    performance: {
      invested: 14000000,
      unrealized_profit: 1000000,
      unrealized_rate: 7.14,
      today_change: 250000,
      today_change_rate: 1.69,
    },
    safety: {
      level: 'healthy',
      summary: '모든 상태가 정상입니다.',
      price_updated_at: '2026-11-09T14:00:00Z',
      unresolved_orders: 0,
    },
    recommendations: [
      { code: 'KRW-BTC', name: '비트코인', temp_price: 130000000, setting_price: 125000000, ma_period: 40 },
      { code: 'KRW-ETH', name: '이더리움', temp_price: 4500000, setting_price: 4400000, ma_period: 40 },
    ],
    assets: [
      { currency: 'KRW', name: '원화', balance: '5000000', valuation: 5000000, profit_rate: null },
      { currency: 'BTC', name: '비트코인', balance: '0.05', valuation: 6500000, profit_rate: 5.2 },
      { currency: 'XRP', name: '리플', balance: '1000', valuation: 3500000, profit_rate: -3.5 },
    ],
    recent_orders: [
      { uuid: 'o-1', created_at: '2026-11-09T13:00:00Z', market: 'KRW-BTC', side: 'bid', ord_type: 'price', price: '1000000', volume: null, executed_volume: '0.0076923', state: 'done' },
      { uuid: 'o-2', created_at: '2026-11-09T12:00:00Z', market: 'KRW-XRP', side: 'ask', ord_type: 'market', price: null, volume: '500', executed_volume: '500', state: 'done' },
      { uuid: 'o-3', created_at: '2026-11-09T11:00:00Z', market: 'KRW-DOGE', side: 'bid', ord_type: 'limit', price: '200', volume: '1000', executed_volume: '0', state: 'wait' },
      { uuid: 'o-4', created_at: '2026-11-09T10:00:00Z', market: 'KRW-ADA', side: 'ask', ord_type: 'limit', price: '1000', volume: '100', executed_volume: '40', state: 'cancel' },
    ],
  };

  it('renders all performance cards in metric grid', () => {
    const html = renderToStaticMarkup(<Monitor data={sampleDashboard} refresh={() => {}} />);
    expect(html).toContain('총 평가액');
    expect(html).toContain('₩15,000,000');
    expect(html).toContain('총매수금액');
    expect(html).toContain('₩14,000,000');
    expect(html).toContain('평가손익 (수익률)');
    expect(html).toContain('+₩1,000,000');
    expect(html).toContain('(+7.14%)');
    expect(html).toContain('당일 변동금액 (변동률)');
    expect(html).toContain('+₩250,000');
    expect(html).toContain('(+1.69%)');
    expect(html).toContain('이동평균 매수 신호');
    expect(html).toContain('2개');
    expect(html).toContain('오늘 체결');
    expect(html).toContain('3건');
  });

  it('renders Korean order statuses and details in recent orders table', () => {
    const html = renderToStaticMarkup(<Monitor data={sampleDashboard} refresh={() => {}} />);
    // Done state translated to 체결
    expect(html).toContain('체결');
    // Wait state translated to 대기
    expect(html).toContain('대기');
    // Partially filled limit sell cancelled translated to 일부 체결 · 취소
    expect(html).toContain('일부 체결 · 취소');
    // Market buy price and volume
    expect(html).toContain('시장가 (₩1,000,000)');
    // Market sell price
    expect(html).toContain('시장가');
    // Limit price
    expect(html).toContain('₩200');
  });

  it('renders asset strategy status badges and emergency sell buttons', () => {
    const html = renderToStaticMarkup(<Monitor data={sampleDashboard} refresh={() => {}} />);
    // KRW is cash
    expect(html).toContain('현금');
    // BTC is in recommendations -> HOLD
    expect(html).toContain('HOLD');
    // XRP is NOT in recommendations -> 매도 신호
    expect(html).toContain('매도 신호');
    // Emergency sell buttons for crypto assets
    expect(html).toContain('긴급 매도');
  });

  it('displays warning banner and reconcile button when blocked or unresolved orders exist', () => {
    const blockedData = {
      ...sampleDashboard,
      safety: {
        level: 'blocked',
        summary: '미확인 체결 1건 발생으로 주문이 중단되었습니다.',
        unresolved_orders: 1,
      },
    };
    const html = renderToStaticMarkup(<Monitor data={blockedData} refresh={() => {}} />);
    expect(html).toContain('주문 미확인 경고');
    expect(html).toContain('주문 상태 재확인(Reconcile)');
    expect(html).toContain('미확인 체결 1건 발생으로 주문이 중단되었습니다.');
  });

  it('displays warning banner and correct unresolvedCount when unresolved_orders is an array of objects', () => {
    const blockedDataWithArray = {
      ...sampleDashboard,
      safety: {
        level: 'blocked',
        summary: '미확인 주문 대기',
        unresolved_orders: [
          { identifier: 'auto-ord-1', market: 'KRW-BTC' },
          { identifier: 'auto-ord-2', market: 'KRW-ETH' },
          { identifier: 'auto-ord-3', market: 'KRW-XRP' },
        ],
      },
    };
    const html = renderToStaticMarkup(<Monitor data={blockedDataWithArray} refresh={() => {}} />);
    expect(html).toContain('주문 미확인 경고');
    expect(html).toContain('미확인 주문 수: <b>3건</b>');
  });

  it('displays warning banner and 0건 when unresolved_orders is empty array', () => {
    const blockedDataEmpty = {
      ...sampleDashboard,
      safety: {
        level: 'blocked',
        summary: '미확인 주문 없음',
        unresolved_orders: [],
      },
    };
    const html = renderToStaticMarkup(<Monitor data={blockedDataEmpty} refresh={() => {}} />);
    expect(html).toContain('주문 미확인 경고');
    expect(html).toContain('미확인 주문 수: <b>0건</b>');
  });

  it('renders per-recommendation backtest button, auto-buy toggle, and global MA period', () => {
    const dashWithGlobalStrategy = {
      ...sampleDashboard,
      strategy_settings: {
        ma_period: 60,
        days: 150,
        initial_capital: 2000000,
        fee_bps: 5,
        slippage_bps: 10,
      },
      recommendations: [
        { code: 'KRW-BTC', name: '비트코인', temp_price: 130000000, setting_price: 125000000, ma_period: 60, auto_trade: true },
        { code: 'KRW-ETH', name: '이더리움', temp_price: 4500000, setting_price: 4400000, ma_period: 60, auto_trade: false },
      ],
    };
    const html = renderToStaticMarkup(<Monitor data={dashWithGlobalStrategy} refresh={() => {}} />);
    expect(html).toContain('MA60');
    expect(html).toContain('rec-backtest-btn');
    expect(html).toContain('백테스트');
    expect(html).toContain('rec-auto-btn active');
    expect(html).toContain('자동매수 켜짐');
    expect(html).toContain('자동매수 허용');
    expect(html).toContain('자동매수 허용 1종목');
    expect(html).toContain('매수 1순위');
  });

  it('renders dropped auto-trade markets panel and dust asset status properly', () => {
    const dashWithEdgeCases = {
      ...sampleDashboard,
      auto_trade_markets: ['KRW-BTC', 'KRW-SOL'],
      inactive_auto_trade_items: [
        {
          code: 'KRW-SOL',
          name: '솔라나',
          temp_price: 210000,
          setting_price: 225000,
          ma_period: 40,
          auto_trade: true,
          status: 'SIGNAL_DROPPED',
        },
      ],
      recommendations: [
        { code: 'KRW-BTC', name: '비트코인', temp_price: 130000000, setting_price: 125000000, ma_period: 40, auto_trade: true },
      ],
      assets: [
        { currency: 'KRW', name: '원화', balance: '500000', quantity: 500000, valuation: 500000 },
        { currency: 'DOGE', name: '도지코인', balance: '10', quantity: 10, valuation: 2000, profit_rate: -5.0, unsellable_reason: 'dust' },
      ],
    };
    const html = renderToStaticMarkup(<Monitor data={dashWithEdgeCases} refresh={() => {}} />);
    expect(html).toContain('자동매수 허용 2종목 (활성 1 · 신호이탈 1)');
    expect(html).toContain('신호 이탈 · 대기 중인 자동매수 종목 (1개)');
    expect(html).toContain('솔라나');
    expect(html).toContain('신호 이탈 종목 모두 해제');
    expect(html).toContain('자동매수 해제');
    expect(html).toContain('소액 잔고 (매매 제외)');
    expect(html).toContain('소액 매도불가');
  });

  it('sorts recommendations by backtest return descending and updates buy priority ranks and negative return blockers', () => {
    const dashWithBacktestMetrics = {
      ...sampleDashboard,
      strategy_settings: {
        candle_interval: 'days',
        ma_period: 40,
        sort_by: 'bt_return_desc',
        exclude_negative_bt: true,
      },
      recommendations: [
        {
          code: 'KRW-LOW',
          name: '고괴리저수익코인',
          temp_price: 1200,
          setting_price: 1000, // +20% spread
          ma_period: 40,
          auto_trade: true,
          bt_return_pct: -8.45,
          bt_excess_pct: -12.1,
          bt_mdd_pct: 24.5,
          bt_win_rate_pct: 25,
          bt_trade_count: 4,
        },
        {
          code: 'KRW-HIGH',
          name: '저괴리고수익코인',
          temp_price: 1030,
          setting_price: 1000, // +3% spread
          ma_period: 40,
          auto_trade: true,
          bt_return_pct: 42.8,
          bt_excess_pct: 18.4,
          bt_mdd_pct: 9.2,
          bt_win_rate_pct: 75,
          bt_trade_count: 8,
        },
        {
          code: 'KRW-MID',
          name: '중수익코인',
          temp_price: 1080,
          setting_price: 1000, // +8% spread
          ma_period: 40,
          auto_trade: true,
          bt_return_pct: 15.2,
          bt_excess_pct: 4.1,
          bt_mdd_pct: 14.0,
          bt_win_rate_pct: 60,
          bt_trade_count: 5,
        },
      ],
    };

    const html = renderToStaticMarkup(<Monitor data={dashWithBacktestMetrics} refresh={() => {}} />);

    // Verify card order follows bt_return_desc: KRW-HIGH (+42.80%) -> KRW-MID (+15.20%) -> KRW-LOW (-8.45%)
    const idxHigh = html.indexOf('저괴리고수익코인');
    const idxMid = html.indexOf('중수익코인');
    const idxLow = html.indexOf('고괴리저수익코인');
    expect(idxHigh).toBeGreaterThan(-1);
    expect(idxMid).toBeGreaterThan(idxHigh);
    expect(idxLow).toBeGreaterThan(idxMid);

    // Verify backtest strip badges are rendered on cards
    expect(html).toContain('백테스트 +42.80%');
    expect(html).toContain('초과 +18.4%p');
    expect(html).toContain('MDD 9.2%');
    expect(html).toContain('승률 75% (8회)');
    expect(html).toContain('백테스트 -8.45%');

    // Verify priority rank calculation with exclude_negative_bt=true:
    // KRW-HIGH gets rank 1, KRW-MID gets rank 2, and KRW-LOW is blocked from auto-buy rank
    const sorted = sortRecommendations(dashWithBacktestMetrics.recommendations, 'bt_return_desc');
    const { enabledRankByCode, blockedNegativeByCode } = computeEnabledRanks(
      sorted,
      r => Boolean(r.auto_trade),
      true
    );
    expect(enabledRankByCode['KRW-HIGH']).toBe(1);
    expect(enabledRankByCode['KRW-MID']).toBe(2);
    expect(enabledRankByCode['KRW-LOW']).toBeUndefined();
    expect(blockedNegativeByCode['KRW-LOW']).toBe(true);
    expect(html).toContain('매수 1순위');
    expect(html).toContain('매수 2순위');
    expect(html).toContain('자동매수 차단 (수익률 음수)');
  });

  it('filters out negative backtest return recommendations when hideNegativeBt is enabled', () => {
    const dashForFilter = {
      ...sampleDashboard,
      recommendations: [
        {
          code: 'KRW-POS',
          name: '양수수익코인',
          temp_price: 1100,
          setting_price: 1000,
          ma_period: 40,
          auto_trade: false,
          bt_return_pct: 21.5,
          bt_excess_pct: 6.2,
          bt_mdd_pct: 11.4,
        },
        {
          code: 'KRW-NEG',
          name: '음수손실코인',
          temp_price: 1150,
          setting_price: 1000,
          ma_period: 40,
          auto_trade: true,
          bt_return_pct: -14.3,
          bt_excess_pct: -9.0,
          bt_mdd_pct: 28.0,
        },
      ],
    };

    const html = renderToStaticMarkup(
      <Monitor data={dashForFilter} refresh={() => {}} initialFilters={{ hideNegativeBt: true }} />
    );

    expect(html).toContain('양수수익코인');
    expect(html).not.toContain('음수손실코인');
    expect(html).toContain('표시 종목 <b>1</b> / 2개');
    expect(html).toContain('마이너스 수익률 1종목');
    expect(html).toContain('마이너스 수익률 허용 종목 해제 (1개)');

    // Also verify filterRecommendations helper for excess return and MDD filters
    const excessOnly = filterRecommendations(dashForFilter.recommendations, { onlyPositiveExcess: true });
    expect(excessOnly.map(r => r.code)).toEqual(['KRW-POS']);
    const lowMdd = filterRecommendations(dashForFilter.recommendations, { lowMddOnly: true });
    expect(lowMdd.map(r => r.code)).toEqual(['KRW-POS']);
  });

  it('calls PUT /api/upbit/auto-markets with expected markets for smart batch actions', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    // 1. Batch-enable positive backtest return markets
    await batchUpdateAutoTradeMarkets(['KRW-HIGH', 'KRW-MID'], true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/upbit/auto-markets');
    expect(fetchMock.mock.calls[0][1].method).toBe('PUT');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      market: 'KRW-HIGH',
      markets: ['KRW-HIGH', 'KRW-MID'],
      auto_trade: true,
    });

    // 2. Batch-disable negative backtest return markets
    await batchUpdateAutoTradeMarkets(['KRW-NEG'], false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      market: 'KRW-NEG',
      markets: ['KRW-NEG'],
      auto_trade: false,
    });
  });

  it('renders BacktestEquityCurve SVG with baseline and min/max equity labels', () => {
    const sampleCurve = [
      { date: '2026-06-01', equity: 1000000 },
      { date: '2026-08-01', equity: 940000 },
      { date: '2026-11-01', equity: 1280000 },
    ];
    const html = renderToStaticMarkup(
      <BacktestEquityCurve curve={sampleCurve} initialCapital={1000000} />
    );
    expect(html).toContain('자산 추이 곡선 (Equity Curve)');
    expect(html).toContain('최저 ₩940,000');
    expect(html).toContain('기준 ₩1,000,000');
    expect(html).toContain('최고 ₩1,280,000');
    expect(html).toContain('2026-06-01');
    expect(html).toContain('2026-11-01');
    expect(html).toContain('<polyline');
  });
});

describe('Settings component', () => {
  const sampleDash = {
    auto_on: false,
    key_registered: true,
    strategy_settings: {
      ma_period: 45,
      days: 160,
      initial_capital: 3000000,
      fee_bps: 5,
      slippage_bps: 10,
    },
  };

  it('renders global strategy/backtest settings, Upbit API Key section, IP copy button, and auto-trade button', () => {
    const html = renderToStaticMarkup(<Settings dashboard={sampleDash} onChanged={() => {}} />);
    expect(html).toContain('전체 전략 및 백테스트 설정');
    expect(html).toContain('30분봉');
    expect(html).toContain('1시간봉');
    expect(html).toContain('4시간봉');
    expect(html).toContain('일봉');
    expect(html).toContain('주봉');
    expect(html).toContain('기준 일봉 수 (MA)');
    expect(html).toContain('백테스트 기간(일)');
    expect(html).toContain('백테스트 초기 자금(원)');
    expect(html).toContain('전체 설정 저장');
    expect(html).toContain('45일 단순 이동평균(일봉 MA45)');
    expect(html).toContain('Upbit API 연결');
    expect(html).toContain('공인 IP 복사');
    expect(html).toContain('실제 자동매매');
    expect(html).toContain('자동매매 켜기');
  });

  it('renders active auto-trade state properly', () => {
    const activeDash = { auto_on: true, key_registered: true };
    const html = renderToStaticMarkup(<Settings dashboard={activeDash} onChanged={() => {}} />);
    expect(html).toContain('자동매매 끄기');
    expect(html).toContain('실제 주문이 활성화되어 있습니다.');
  });
});

describe('Login component & Brand / PWA Install Modal', () => {
  it('renders login form with Korean labels, brand logo, and app download button', () => {
    const html = renderToStaticMarkup(<Login onLogin={() => {}} />);
    expect(html).toContain('UPBIT MA40 AUTO TRADER');
    expect(html).toContain('40일 이동평균 자동매매');
    expect(html).toContain('MA40 Auto Trader 로고');
    expect(html).toContain('모바일·PC 전용 앱 다운로드 (홈 화면 설치)');
    expect(html).toContain('아이디');
    expect(html).toContain('비밀번호');
    expect(html).toContain('로그인');
  });

  it('renders BrandLogo and AppInstallModal with native and platform install guides', () => {
    const logoHtml = renderToStaticMarkup(<BrandLogo size={56} />);
    expect(logoHtml).toContain('MA40 Auto Trader 로고');
    expect(logoHtml).toContain('viewBox="0 0 512 512"');

    const modalHtml = renderToStaticMarkup(
      <AppInstallModal
        open={true}
        onClose={() => {}}
        pwa={{ canNativeInstall: true, isInstalled: false, isIos: false, triggerInstall: async () => ({ outcome: 'accepted' }) }}
      />
    );
    expect(modalHtml).toContain('MA40 오토 트레이더 앱 다운로드');
    expect(modalHtml).toContain('지금 바로 앱 다운로드 (원클릭 설치)');
    expect(modalHtml).toContain('Android · PC (Chrome / Edge / 삼성 인터넷)');
    expect(modalHtml).toContain('iPhone · iPad (Safari 브라우저)');
  });
});
