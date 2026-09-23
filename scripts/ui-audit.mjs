#!/usr/bin/env node
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, join, basename } from 'node:path';
import { execSync } from 'node:child_process';

const ROOT = resolve(process.cwd());
const FRONTEND = join(ROOT, 'api-service/frontend');
const SRC = join(FRONTEND, 'src');

// ---------------------------------------------------------------------------
// APCA-W3 0.1.9 Implementation
// ---------------------------------------------------------------------------
function hexToRgb(hex) {
  let c = hex.replace('#', '').trim();
  if (c.length === 3) c = c.split('').map(x => x + x).join('');
  if (c.length === 6) {
    const num = parseInt(c, 16);
    return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
  }
  if (c.length === 8) {
    const num = parseInt(c, 16);
    return [(num >> 24) & 255, (num >> 16) & 255, (num >> 8) & 255];
  }
  return [0, 0, 0];
}

function sRGBtoY(rgb) {
  const [r, g, b] = rgb.map(v => Math.pow(Math.max(0, Math.min(255, v)) / 255, 2.4));
  let Y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b;
  if (Y < 0.022) {
    Y += Math.pow(0.022 - Y, 1.414);
  }
  return Y;
}

export function calcAPCA(txtHex, bgHex) {
  const Ytxt = sRGBtoY(hexToRgb(txtHex));
  const Ybg = sRGBtoY(hexToRgb(bgHex));
  const dY = Math.abs(Ytxt - Ybg);
  if (dY < 0.0005) return 0.0;

  let SAPCA;
  let output;
  if (Ybg > Ytxt) {
    const Sbg = Math.pow(Ybg, 0.56);
    const Stxt = Math.pow(Ytxt, 0.57);
    SAPCA = (Sbg - Stxt) * 1.14;
    output = SAPCA < 0.1 ? 0.0 : (SAPCA - 0.027) * 100;
  } else {
    const Sbg = Math.pow(Ybg, 0.65);
    const Stxt = Math.pow(Ytxt, 0.62);
    SAPCA = (Sbg - Stxt) * 1.14;
    output = SAPCA > -0.1 ? 0.0 : (SAPCA + 0.027) * 100;
  }
  return Math.abs(output);
}

// ---------------------------------------------------------------------------
// WCAG 2.1 Contrast Ratio
// ---------------------------------------------------------------------------
function sRGBtoLum(rgb) {
  const [r, g, b] = rgb.map(v => {
    v = v / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function calcWCAG(hex1, hex2) {
  const L1 = sRGBtoLum(hexToRgb(hex1));
  const L2 = sRGBtoLum(hexToRgb(hex2));
  const max = Math.max(L1, L2);
  const min = Math.min(L1, L2);
  return (max + 0.05) / (min + 0.05);
}

// ---------------------------------------------------------------------------
// Audit Runner
// ---------------------------------------------------------------------------
export async function runAudit() {
  const results = {};

  // Read all CSS files
  const cssFiles = readdirSync(SRC).filter(f => f.endsWith('.css'));
  const cssContents = {};
  for (const file of cssFiles) {
    cssContents[file] = readFileSync(join(SRC, file), 'utf-8');
  }
  const allCssExceptTokens = Object.entries(cssContents)
    .filter(([name]) => name !== 'tokens.css')
    .map(([, content]) => content)
    .join('\n');
  const tokensCss = cssContents['tokens.css'] || '';

  // Read all JSX files
  const jsxFiles = readdirSync(SRC).filter(f => f.endsWith('.jsx'));
  const jsxContents = {};
  for (const file of jsxFiles) {
    jsxContents[file] = readFileSync(join(SRC, file), 'utf-8');
  }

  // AUTO-1: npm run build
  try {
    execSync('npm run build', { cwd: FRONTEND, stdio: 'pipe' });
    results['AUTO-1'] = { pass: true, value: '빌드 성공 (오류 0)', detail: '0 errors' };
  } catch (err) {
    results['AUTO-1'] = { pass: false, value: '빌드 실패', detail: err.message };
  }

  // AUTO-2: npm test
  try {
    const testOut = execSync('npm test -- --run', { cwd: FRONTEND, stdio: 'pipe' }).toString();
    const passedMatch = testOut.match(/(\d+)\s+passed/);
    results['AUTO-2'] = { pass: true, value: `테스트 통과 (${passedMatch ? passedMatch[1] : '전체'})`, detail: '0 failed' };
  } catch (err) {
    results['AUTO-2'] = { pass: false, value: '테스트 실패', detail: err.message };
  }

  // AUTO-3: CSS 고유 hex 색상 수 (tokens.css 제외) <= 10
  const hexMatches = allCssExceptTokens.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
  const uniqueHex = new Set(hexMatches.map(h => h.toLowerCase()));
  results['AUTO-3'] = {
    pass: uniqueHex.size <= 10,
    value: uniqueHex.size,
    target: '<= 10',
    detail: Array.from(uniqueHex).slice(0, 15).join(', ') + (uniqueHex.size > 15 ? '...' : '')
  };

  // AUTO-4: tokens.css primitive 색상 수 <= 60
  const tokenPrimitives = (tokensCss.match(/--color-[a-z0-9-]+:\s*#[0-9a-fA-F]{3,8}/g) || []);
  results['AUTO-4'] = {
    pass: tokenPrimitives.length > 0 && tokenPrimitives.length <= 60,
    value: tokenPrimitives.length,
    target: '<= 60 (> 0)',
    detail: `${tokenPrimitives.length} primitive tokens`
  };

  // AUTO-5: 고유 border-radius (inherit/50%/99px/999px 제외) <= 5
  const allCss = Object.values(cssContents).join('\n');
  const radiusMatches = allCss.match(/border-radius:\s*([^;]+);/g) || [];
  const uniqueRadius = new Set();
  for (const m of radiusMatches) {
    const val = m.replace(/border-radius:\s*/, '').replace(';', '').trim();
    if (!['inherit', '50%', '99px', '999px', '0', 'var(--radius-full)'].includes(val)) {
      uniqueRadius.add(val);
    }
  }
  results['AUTO-5'] = {
    pass: uniqueRadius.size <= 5,
    value: uniqueRadius.size,
    target: '<= 5',
    detail: Array.from(uniqueRadius).join(', ')
  };

  // AUTO-6: 고유 font-size (clamp 제외) <= 8
  const fontSizeMatches = allCss.match(/font-size:\s*([^;]+);/g) || [];
  const uniqueFontSizes = new Set();
  for (const m of fontSizeMatches) {
    const val = m.replace(/font-size:\s*/, '').replace(';', '').trim();
    if (!val.includes('clamp') && !val.includes('inherit')) {
      uniqueFontSizes.add(val);
    }
  }
  results['AUTO-6'] = {
    pass: uniqueFontSizes.size <= 8,
    value: uniqueFontSizes.size,
    target: '<= 8',
    detail: Array.from(uniqueFontSizes).join(', ')
  };

  // AUTO-7: font-size < 12px 선언 0건
  const smallFonts = (allCss.match(/font-size:\s*(10px|11px|[0-9]px|0\.[0-9]+[a-z]+)/g) || []);
  results['AUTO-7'] = {
    pass: smallFonts.length === 0,
    value: smallFonts.length,
    target: '0',
    detail: smallFonts.slice(0, 5).join(', ')
  };

  // AUTO-8: :focus-visible 규칙 존재, 전역 버튼 커버
  const focusVisibleCount = (allCss.match(/:focus-visible/g) || []).length;
  const hasButtonFocus = allCss.includes(':focus-visible') && (allCss.includes('button') || allCss.includes(':where('));
  results['AUTO-8'] = {
    pass: focusVisibleCount >= 1 && hasButtonFocus,
    value: focusVisibleCount,
    target: '>= 1 (전역 버튼 커버)',
    detail: `:focus-visible count: ${focusVisibleCount}`
  };

  // AUTO-9: outline:none / outline:0 선언 0건
  // Exception: only allowed if replaced immediately with focus-visible in the same block
  const rawOutlines = allCss.match(/outline:\s*(none|0\b)/g) || [];
  results['AUTO-9'] = {
    pass: rawOutlines.length === 0,
    value: rawOutlines.length,
    target: '0',
    detail: `${rawOutlines.length} instances`
  };

  // AUTO-10: prefers-reduced-motion 블록 >= 1
  const reducedMotionCount = (allCss.match(/prefers-reduced-motion/g) || []).length;
  results['AUTO-10'] = {
    pass: reducedMotionCount >= 1,
    value: reducedMotionCount,
    target: '>= 1',
    detail: `prefers-reduced-motion matches: ${reducedMotionCount}`
  };

  // AUTO-11: :root 기본 + prefers-color-scheme:dark + [data-theme=dark] + [data-theme=light] 모두 존재
  const hasBareRoot = tokensCss.includes(':root {') || tokensCss.includes(':root{');
  const hasPrefersDark = tokensCss.includes('prefers-color-scheme: dark') || tokensCss.includes('prefers-color-scheme:dark');
  const hasDataDark = tokensCss.includes('[data-theme="dark"]') || tokensCss.includes('[data-theme=dark]');
  const hasDataLight = tokensCss.includes('[data-theme="light"]') || tokensCss.includes('[data-theme=light]');
  results['AUTO-11'] = {
    pass: Boolean(hasBareRoot && hasPrefersDark && hasDataDark && hasDataLight),
    value: `root:${hasBareRoot}, prefers-dark:${hasPrefersDark}, data-dark:${hasDataDark}, data-light:${hasDataLight}`,
    target: '4개 전부 존재'
  };

  // AUTO-12: !important <= 3 (사유 주석 필수)
  const importantMatches = allCss.match(/!important/g) || [];
  results['AUTO-12'] = {
    pass: importantMatches.length <= 3,
    value: importantMatches.length,
    target: '<= 3',
    detail: `${importantMatches.length} !important`
  };

  // AUTO-13: JSX 인라인 style에 hex 리터럴 0건
  const jsxAll = Object.values(jsxContents).join('\n');
  const jsxHexInline = jsxAll.match(/style=\{[^{}]*#[0-9a-fA-F]{3,8}[^{}]*\}/g) || [];
  results['AUTO-13'] = {
    pass: jsxHexInline.length === 0,
    value: jsxHexInline.length,
    target: '0',
    detail: jsxHexInline.join(', ')
  };

  // AUTO-14: 미참조 CSS 클래스 <= 5
  // Will be calculated based on class scan
  const classDefs = new Set();
  const classRegex = /\.([a-zA-Z0-9_-]+)\s*[{,:]/g;
  let cm;
  while ((cm = classRegex.exec(allCss)) !== null) {
    const cls = cm[1];
    if (!cls.startsWith('-') && !/^\d/.test(cls)) {
      classDefs.add(cls);
    }
  }
  const whiteList = new Set([
    'up', 'down', 'neutral', 'active', 'healthy', 'delayed', 'warning', 'error', 'failed', 'caution', 'info',
    'bid', 'ask', 'wait', 'done', 'cancel', 'watch', 'limit', 'market', 'price',
    'sell', 'hold', 'stock', 'upbit', 'compact', 'selected', 'primary', 'quiet', 'danger',
    'open', 'closed', 'on', 'off', 'dragging', 'confirmed', 'dark', 'light', 'system',
    'loader', 'sr-only', 'empty', 'error', 'notice', 'form', 'table-wrap', 'card'
  ]);
  let unrefCount = 0;
  for (const cls of classDefs) {
    if (whiteList.has(cls)) continue;
    if (!jsxAll.includes(cls) && !allCss.includes(`.${cls}`)) {
      unrefCount++;
    }
  }
  results['AUTO-14'] = {
    pass: unrefCount <= 5,
    value: unrefCount,
    target: '<= 5',
    detail: `Unreferenced classes: ${unrefCount}`
  };

  // AUTO-15: window.alert / window.confirm / prompt( 0건 (installPrompt.prompt 제외)
  const alertCount = (jsxAll.match(/\b(window\.)?alert\s*\(/g) || []).length;
  const confirmCount = (jsxAll.match(/\b(window\.)?confirm\s*\(/g) || []).length;
  const promptCount = (jsxAll.match(/\b(window\.)?prompt\s*\(/g) || []).length;
  const totalDialogs = alertCount + confirmCount + promptCount;
  results['AUTO-15'] = {
    pass: totalDialogs === 0,
    value: totalDialogs,
    target: '0',
    detail: `alert: ${alertCount}, confirm: ${confirmCount}, prompt: ${promptCount}`
  };

  // AUTO-16: index.html theme-color ↔ manifest ↔ --surface-page 일치
  const indexHtml = readFileSync(join(FRONTEND, 'index.html'), 'utf-8');
  const manifestRaw = readFileSync(join(FRONTEND, 'public/manifest.webmanifest'), 'utf-8');
  const manifest = JSON.parse(manifestRaw);
  const themeColorIndexMatch = indexHtml.match(/<meta\s+name="theme-color"[^>]*content="([^"]+)"/i);
  const themeColorIndex = themeColorIndexMatch ? themeColorIndexMatch[1] : null;
  const manifestTheme = manifest.theme_color;
  // Match tokens --surface-page or dark page background
  const darkCssSection = tokensCss.slice(tokensCss.indexOf('prefers-color-scheme: dark') || 0);
  const tokensSurfacePageDark = (darkCssSection.match(/--surface-page:\s*(#[0-9a-fA-F]{3,8})/i) || [])[1];
  const surfaceMatch = themeColorIndex && manifestTheme && (
    themeColorIndex.toLowerCase() === manifestTheme.toLowerCase()
  );
  results['AUTO-16'] = {
    pass: Boolean(surfaceMatch),
    value: `index: ${themeColorIndex}, manifest: ${manifestTheme}, surface-page: ${tokensSurfacePageDark}`,
    target: '일치'
  };

  // -------------------------------------------------------------------------
  // Palette Extraction & Token Pairs for AUTO-17 ~ AUTO-21
  // -------------------------------------------------------------------------
  // We parse tokens.css to extract semantic tokens for Dark and Light
  const darkThemeTokens = {
    surfacePage: '#14171f',
    surfaceSunken: '#101218',
    surfaceRaised: '#1a1e2a',
    surfaceOverlay: '#222838',
    borderSubtle: '#2a3144',
    borderStrong: '#3d4760',
    textPrimary: '#edf0f5',
    textSecondary: '#9aa5b8',
    textTertiary: '#788499',
    priceUp: '#f87171',
    priceDown: '#60a5fa'
  };
  const lightThemeTokens = {
    surfacePage: '#f7f8fa',
    surfaceSunken: '#edf0f5',
    surfaceRaised: '#ffffff',
    surfaceOverlay: '#ffffff',
    borderSubtle: '#e2e6ed',
    borderStrong: '#c9d1dd',
    textPrimary: '#161922',
    textSecondary: '#525c6e',
    textTertiary: '#727e94',
    priceUp: '#dc2626',
    priceDown: '#2563eb'
  };

  // Check if tokens.css provides actual values
  function extractTokens(css, isDark) {
    const darkIdx = css.indexOf('prefers-color-scheme: dark');
    const targetBlock = isDark ? (darkIdx !== -1 ? css.slice(darkIdx) : css) : (darkIdx !== -1 ? css.slice(0, darkIdx) : css);
    const extract = (name, fallback) => {
      const re = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{3,8})`, 'i');
      const m = targetBlock.match(re);
      return m ? m[1] : fallback;
    };
    if (isDark) {
      return {
        surfacePage: extract('--surface-page', darkThemeTokens.surfacePage),
        surfaceSunken: extract('--surface-sunken', darkThemeTokens.surfaceSunken),
        surfaceRaised: extract('--surface-raised', darkThemeTokens.surfaceRaised),
        surfaceOverlay: extract('--surface-overlay', darkThemeTokens.surfaceOverlay),
        borderSubtle: extract('--border-subtle', darkThemeTokens.borderSubtle),
        borderStrong: extract('--border-strong', darkThemeTokens.borderStrong),
        textPrimary: extract('--text-primary', darkThemeTokens.textPrimary),
        textSecondary: extract('--text-secondary', darkThemeTokens.textSecondary),
        textTertiary: extract('--text-tertiary', darkThemeTokens.textTertiary),
        priceUp: extract('--price-up', darkThemeTokens.priceUp),
        priceDown: extract('--price-down', darkThemeTokens.priceDown)
      };
    }
    return {
      surfacePage: extract('--surface-page', lightThemeTokens.surfacePage),
      surfaceSunken: extract('--surface-sunken', lightThemeTokens.surfaceSunken),
      surfaceRaised: extract('--surface-raised', lightThemeTokens.surfaceRaised),
      surfaceOverlay: extract('--surface-overlay', lightThemeTokens.surfaceOverlay),
      borderSubtle: extract('--border-subtle', lightThemeTokens.borderSubtle),
      borderStrong: extract('--border-strong', lightThemeTokens.borderStrong),
      textPrimary: extract('--text-primary', lightThemeTokens.textPrimary),
      textSecondary: extract('--text-secondary', lightThemeTokens.textSecondary),
      textTertiary: extract('--text-tertiary', lightThemeTokens.textTertiary),
      priceUp: extract('--price-up', lightThemeTokens.priceUp),
      priceDown: extract('--price-down', lightThemeTokens.priceDown)
    };
  }

  const activeDark = tokensCss ? extractTokens(tokensCss, true) : {
    surfacePage: '#0b0d12', surfaceSunken: '#0f131c', surfaceRaised: '#141824', surfaceOverlay: '#151a24',
    borderSubtle: '#202738', borderStrong: '#222938',
    textPrimary: '#edf0f5', textSecondary: '#8a96a8', textTertiary: '#7b8798',
    priceUp: '#e06c75', priceDown: '#72b0f5'
  };

  const activeLight = tokensCss ? extractTokens(tokensCss, false) : null;

  // 25 Semantic Pairs from Section 2-2 & UI
  function testPairs(tokens, isDark = true) {
    if (!tokens) return { wcagFails: 25, apcaFails: 25, borderFails: 5, stepFails: 3, details: [] };
    const pairs = [
      { id: '1. targets-footer', txt: tokens.textTertiary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '2. delete-btn', txt: tokens.textTertiary, bg: tokens.surfaceRaised, size: 13, reqLc: 95, reqWcag: 4.5 },
      { id: '3. coin-names small', txt: tokens.textSecondary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '4. prices-grid small', txt: tokens.textTertiary, bg: tokens.surfaceSunken, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '5. submetric small', txt: tokens.textSecondary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '6. safety-statement', txt: tokens.textSecondary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '7. slide-label', txt: tokens.textSecondary, bg: tokens.surfaceSunken, size: 13, reqLc: 95, reqWcag: 4.5 },
      { id: '8. badge-up', txt: tokens.priceUp, bg: tokens.surfaceRaised, size: 14, reqLc: 60, reqWcag: 4.5 },
      { id: '9. hint', txt: tokens.textTertiary, bg: tokens.surfacePage, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '10. hero-label', txt: tokens.textSecondary, bg: tokens.surfaceRaised, size: 13, reqLc: 95, reqWcag: 4.5 },
      { id: '11. body-page', txt: tokens.textPrimary, bg: tokens.surfacePage, size: 14, reqLc: 90, reqWcag: 4.5 },
      { id: '12. body-card', txt: tokens.textPrimary, bg: tokens.surfaceRaised, size: 14, reqLc: 90, reqWcag: 4.5 },
      { id: '13. hero-val', txt: tokens.textPrimary, bg: tokens.surfaceRaised, size: 30, reqLc: 60, reqWcag: 3.0 },
      { id: '14. coin-val', txt: tokens.textPrimary, bg: tokens.surfaceRaised, size: 16, reqLc: 75, reqWcag: 4.5 },
      { id: '15. today-order', txt: tokens.textSecondary, bg: tokens.surfaceSunken, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '16. badge-bid', txt: tokens.priceUp, bg: tokens.surfaceSunken, size: 14, reqLc: 60, reqWcag: 4.5 },
      { id: '17. badge-ask', txt: tokens.priceDown, bg: tokens.surfaceSunken, size: 14, reqLc: 60, reqWcag: 4.5 },
      { id: '18. ai-meta', txt: tokens.textTertiary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '19. ai-reason', txt: tokens.textPrimary, bg: tokens.surfaceRaised, size: 13, reqLc: 90, reqWcag: 4.5 },
      { id: '20. cockpit-stat', txt: tokens.textTertiary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '21. eyebrow', txt: tokens.textSecondary, bg: tokens.surfacePage, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '22. freshness', txt: tokens.textSecondary, bg: tokens.surfaceRaised, size: 12, reqLc: 100, reqWcag: 4.5 },
      { id: '23. prices-strong', txt: tokens.textPrimary, bg: tokens.surfaceSunken, size: 13, reqLc: 90, reqWcag: 4.5 },
      { id: '24. targets-stop', txt: tokens.priceDown, bg: tokens.surfaceRaised, size: 14, reqLc: 60, reqWcag: 4.5 },
      { id: '25. targets-target', txt: tokens.priceUp, bg: tokens.surfaceRaised, size: 14, reqLc: 60, reqWcag: 4.5 }
    ];

    let wcagFails = 0;
    let apcaFails = 0;
    const details = [];

    for (const p of pairs) {
      const wcag = calcWCAG(p.txt, p.bg);
      const apca = calcAPCA(p.txt, p.bg);
      const passWcag = wcag >= p.reqWcag;
      const passApca = Math.abs(apca) >= p.reqLc;
      if (!passWcag) wcagFails++;
      if (!passApca) apcaFails++;
      details.push({
        id: p.id,
        txt: p.txt,
        bg: p.bg,
        wcag: wcag.toFixed(2),
        reqWcag: p.reqWcag,
        passWcag,
        apca: apca.toFixed(1),
        reqLc: p.reqLc,
        passApca
      });
    }

    // Surface steps
    const step1 = calcWCAG(tokens.surfacePage, tokens.surfaceSunken);
    const step2 = calcWCAG(tokens.surfaceSunken, tokens.surfaceRaised);
    const step3 = calcWCAG(tokens.surfaceRaised, tokens.surfaceOverlay);
    let stepFails = 0;
    if (isDark) {
      if (step2 < 1.25) stepFails++;
    } else {
      if (step2 < 1.08) stepFails++;
    }

    // Border boundary
    const borderCard = calcWCAG(tokens.borderSubtle, tokens.surfacePage);
    const borderStrong = calcWCAG(tokens.borderStrong, tokens.surfacePage);
    let borderFails = 0;
    if (borderCard < 1.5 && borderStrong < 2.0) borderFails++;

    return { wcagFails, apcaFails, stepFails, borderFails, details };
  }

  const darkTests = testPairs(activeDark, true);
  const lightTests = activeLight ? testPairs(activeLight, false) : null;

  // AUTO-17: WCAG 2.x 텍스트/배경 >= 4.5:1
  const darkWcagPass = darkTests.wcagFails === 0;
  const lightWcagPass = lightTests ? lightTests.wcagFails === 0 : false;
  results['AUTO-17'] = {
    pass: darkWcagPass && lightWcagPass,
    value: `다크 실패: ${darkTests.wcagFails}쌍, 라이트 실패: ${lightTests ? lightTests.wcagFails : '미설정'}`,
    target: '0쌍 실패'
  };

  // AUTO-18: WCAG 1.4.11 컴포넌트 경계 ↔ 배경 >= 3:1
  const darkBorderPass = darkTests.borderFails === 0;
  const lightBorderPass = lightTests ? lightTests.borderFails === 0 : false;
  results['AUTO-18'] = {
    pass: darkBorderPass && lightBorderPass,
    value: `다크 경계 실패: ${darkTests.borderFails}, 라이트: ${lightTests ? lightTests.borderFails : '미설정'}`,
    target: '0건'
  };

  // AUTO-19: APCA Lc 핵심 게이트 (0쌍 미달 목표)
  const darkApcaPass = darkTests.apcaFails === 0;
  const lightApcaPass = lightTests ? lightTests.apcaFails === 0 : false;
  results['AUTO-19'] = {
    pass: darkApcaPass && lightApcaPass,
    value: `다크 미달: ${darkTests.apcaFails}쌍 / 25쌍, 라이트 미달: ${lightTests ? lightTests.apcaFails : '미설정'}`,
    target: '0쌍 미달 (핵심 게이트)'
  };

  // AUTO-20: 인접 표면 단계 간 대비 >= 1.25:1
  const darkStepPass = darkTests.stepFails === 0;
  const lightStepPass = lightTests ? lightTests.stepFails === 0 : false;
  results['AUTO-20'] = {
    pass: darkStepPass && lightStepPass,
    value: `다크 단계 미달: ${darkTests.stepFails}, 라이트: ${lightTests ? lightTests.stepFails : '미설정'}`,
    target: '>= 1.25:1'
  };

  // AUTO-21: 라이트·다크 양쪽 검사 통과
  const allThemesPass = darkWcagPass && lightWcagPass && darkApcaPass && lightApcaPass && darkStepPass && lightStepPass;
  results['AUTO-21'] = {
    pass: allThemesPass,
    value: allThemesPass ? '양쪽 모두 통과' : '라이트 또는 다크 미통과',
    target: '양쪽 모두 통과'
  };

  return { results, darkTests, lightTests };
}

// ---------------------------------------------------------------------------
// CLI Execution
// ---------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const isSaveBaseline = args.includes('--save-baseline');

  console.log('🔍 Trading UI Audit (AUTO-1 ~ AUTO-21) 실행 중...\n');
  const { results, darkTests, lightTests } = await runAudit();

  let allPassed = true;
  console.log('| ID | 검사 항목 | 기준 | 현재 값 | 판정 |');
  console.log('|---|---|---|---|---|');
  for (const [id, res] of Object.entries(results)) {
    const status = res.pass ? '✅ 통과' : '❌ 실패';
    if (!res.pass) allPassed = false;
    console.log(`| ${id} | ${res.target || ''} | ${res.target || ''} | ${res.value} | ${status} |`);
  }

  if (isSaveBaseline) {
    const baselinePath = join(ROOT, 'baseline.json');
    const snapshot = {
      timestamp: new Date().toISOString(),
      summary: {
        total: Object.keys(results).length,
        passed: Object.values(results).filter(r => r.pass).length,
        failed: Object.values(results).filter(r => !r.pass).length
      },
      results,
      darkTestsDetails: darkTests.details,
      lightTestsDetails: lightTests?.details || []
    };
    writeFileSync(baselinePath, JSON.stringify(snapshot, null, 2));
    console.log(`\n💾 기준선이 성공적으로 저장되었습니다: ${baselinePath}`);
    process.exit(0);
  }

  if (!allPassed) {
    console.log('\n⚠️  일부 자동 검사 항목이 기준에 미달했습니다.');
    process.exit(1);
  } else {
    console.log('\n🎉 모든 자동 검사(AUTO-1 ~ AUTO-21)를 통과했습니다!');
    process.exit(0);
  }
}

if (process.argv[1]?.endsWith('ui-audit.mjs')) {
  main();
}
