import {describe, expect, it} from 'vitest';
import {candidateEligible, candidateRiskLabel, isAnalysisRunning, parseAnalysisSymbols, percentText, sameSettings, settingText, textItems} from './ai';

describe('AI analysis input', () => {
  it('normalizes and deduplicates symbols without altering stock leading zeros', () => {
    expect(parseAnalysisSymbols(' krw-btc, KRW-BTC\nKRW-ETH ', 'upbit')).toEqual(['KRW-BTC', 'KRW-ETH']);
    expect(parseAnalysisSymbols('005930 000660', 'stock')).toEqual(['005930', '000660']);
    expect(parseAnalysisSymbols('', 'stock')).toEqual([]);
  });
  it('rejects non-KRW crypto, malformed stock symbols and more than five instruments', () => {
    expect(() => parseAnalysisSymbols('BTC-ETH', 'upbit')).toThrow('원화 마켓');
    expect(() => parseAnalysisSymbols('5930', 'stock')).toThrow('6자리');
    expect(() => parseAnalysisSymbols('000001 000002 000003 000004 000005 000006', 'stock')).toThrow('최대 5개');
  });
});

describe('AI result presentation', () => {
  it('polls only explicitly pending or running analyses', () => {
    expect(isAnalysisRunning('PENDING')).toBe(true);
    expect(isAnalysisRunning('RUNNING')).toBe(true);
    for (const status of ['FAILED', 'COMPLETED', undefined]) expect(isAnalysisRunning(status)).toBe(false);
  });
  it('does not represent missing or invalid performance as a zero-percent return', () => {
    expect(percentText(null)).toBe('—');
    expect(percentText(undefined)).toBe('—');
    expect(percentText(Infinity)).toBe('—');
    expect(percentText(0)).toBe('0%');
    expect(percentText(-1.25)).toBe('-1.25%');
  });
  it('renders understandable configuration labels and detects changed values', () => {
    expect(settingText('volume_check', false)).toBe('미사용');
    expect(settingText('highest_price_reference_days', 30)).toBe('30일');
    expect(settingText('expected_high_percentage', null)).toBe('확인 불가');
    const setting = {expected_high_percentage: 10, expected_low_percentage: 2, highest_price_reference_days: 30, volume_check: false};
    expect(sameSettings(setting, {...setting})).toBe(true);
    expect(sameSettings(setting, {...setting, volume_check: true})).toBe(false);
    expect(sameSettings(null, setting)).toBe(false);
  });
  it('does not stringify unexpected provider metadata into visible objects', () => {
    expect(textItems(['hello', {message: 'warning'}, {description: 'source'}, {secret: 'omit'}])).toEqual(['hello', 'warning', 'source']);
    expect(textItems(null)).toEqual([]);
  });
  it('labels candidates by how their target/stop width compares to the current setting, not by rank', () => {
    const current = {expected_high_percentage: 25, expected_low_percentage: -12, highest_price_reference_days: 60, volume_check: false};
    expect(candidateRiskLabel({expected_high_percentage: 18, expected_low_percentage: -10}, current)).toEqual({text: '보수적', tone: 'low'});
    expect(candidateRiskLabel({expected_high_percentage: 40, expected_low_percentage: -18}, current)).toEqual({text: '공격적', tone: 'high'});
    expect(candidateRiskLabel({expected_high_percentage: 25, expected_low_percentage: -12, volume_check: true}, current)).toEqual({text: '동일 폭', tone: 'mixed'});
    expect(candidateRiskLabel({expected_high_percentage: 40, expected_low_percentage: -10}, current)).toEqual({text: '변형', tone: 'mixed'});
    expect(candidateRiskLabel(null, current)).toBeNull();
    expect(candidateRiskLabel(current, null)).toBeNull();
  });
  it('allows only verified non-baseline candidates with enough evaluation data', () => {
    const valid = {id: 'candidate-1', validation: {trades: 1, days: 10}};
    expect(candidateEligible(valid)).toBe(true);
    for (const candidate of [null, {...valid, id: 'current'}, {...valid, can_apply: false}, {...valid, validation: null}, {...valid, validation: {trades: 0, days: 30}}, {...valid, validation: {trades: 3, days: 9}}]) {
      expect(candidateEligible(candidate)).toBe(false);
    }
  });
});
