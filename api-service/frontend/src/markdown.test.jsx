import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {MarkdownAnswer, SettingRecommendation} from './AIAnalysis';

describe('MarkdownAnswer', () => {
  it.each([['손절 폭 **10%**를','10%'],['수익률은 **+3.5%**입니다','+3.5%'],['**(주의)**는','(주의)'],['**KRW-BTC**는','KRW-BTC'],['목표 **20%**, 손절','20%']])('renders CJK-adjacent emphasis: %s',(text,bold)=>{
    expect(renderToStaticMarkup(<MarkdownAnswer>{text}</MarkdownAnswer>)).toContain(`<strong>${bold}</strong>`);
  });
  it('preserves non-emphasis stars and code literals',()=>{
    const html=renderToStaticMarkup(<MarkdownAnswer>{'2 ** 3\n\n`**10%**를`\n\n```text\n**+3.5%**입니다\n```'}</MarkdownAnswer>);
    expect(html).toContain('2 ** 3');expect(html).not.toContain('<strong>');expect(html).toContain('**10%**를');
  });
  it('renders readable GFM without executing provider HTML or unsafe links', () => {
    const html = renderToStaticMarkup(<MarkdownAnswer>{`# 결론

- **보유** 유지

| 항목 | 값 |
| --- | --- |
| 수익률 | 3% |

[자료](https://example.com) [위험](javascript:void(0))

<script>void('xss')</script>`}</MarkdownAnswer>);

    expect(html).toContain('<h1>결론</h1>');
    expect(html).toContain('<table>');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('javascript:');
  });
});

describe('SettingRecommendation', () => {
  it('shows the exact values when keeping the current settings', () => {
    const html = renderToStaticMarkup(<SettingRecommendation candidates={[]} baselineSettings={{
      expected_high_percentage: 12,
      expected_low_percentage: -6,
      highest_price_reference_days: 90,
      volume_check: true,
    }}/>);
    expect(html).toContain('현재 계산 설정 유지');
    expect(html).toContain('유지할 계산 설정');
    expect(html).toContain('12%');
    expect(html).toContain('-6%');
    expect(html).toContain('90일');
    expect(html).toContain('사용');
  });
});
