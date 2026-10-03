import {describe,it,expect} from 'vitest';
import {equityRegion,filterEquities,dollarPrice} from './equities';
import {parseAnalysisSymbols} from './ai';

describe('US equity presentation',()=>{
 it('keeps domestic and US currencies distinct',()=>{
  expect(equityRegion({code:'005930'})).toBe('KR');expect(equityRegion({code:'US:AAPL'})).toBe('US');
  expect(dollarPrice(120.25)).toBe('$120.25');expect(dollarPrice(null)).toBe('—');
 });
 it('filters stock and dividend lists without changing rank',()=>{
  const rows=[{code:'US:KO'},{code:'005930'},{code:'US:AAPL'}];
  expect(filterEquities(rows,'US').map(row=>row.code)).toEqual(['US:KO','US:AAPL']);expect(filterEquities(rows,'KR')).toHaveLength(1);
 });
 it('normalizes American tickers alongside Korean codes',()=>{
  expect(parseAnalysisSymbols('aapl, US:AAPL,005930,BRK-B','stock')).toEqual(['US:AAPL','005930','US:BRK-B']);
  expect(()=>parseAnalysisSymbols('US:https://invalid','stock')).toThrow();
  expect(()=>parseAnalysisSymbols('KRW-BTC','stock')).toThrow();
 });
});
