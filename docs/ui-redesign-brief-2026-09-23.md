# Trading 프런트엔드 UI 개선 지시서 (Antigravity 전달용)

작성일 2026-09-23 · 대상 저장소 `api-service/frontend` · 작성 목적: 외부 코딩 에이전트에게 위임할 UI 개선 작업의 범위·기준·반복 루프 정의

---

## 0. 이 문서의 사용법

- **1~3장**은 현재 상태 진단과 근거 수치다. 에이전트가 "무엇이 왜 문제인지" 납득하는 데 쓴다.
- **4장**은 실제 수정 항목이다. P0 → P1 → P2 순서로 처리한다.
- **5장**은 검수 기준(Acceptance Criteria)이다. 각 항목은 통과/실패를 기계적으로 판정할 수 있게 썼다.
- **6장**은 검토 → 수정 → 재검토 루프의 종료 조건이다.
- **7장**이 Antigravity에 그대로 붙여 넣을 프롬프트다.

---

## 1. 프로젝트 컨텍스트

| 항목 | 내용 |
|---|---|
| 성격 | 개인 서버에서 운영하는 주식·Upbit 추천 및 자동매매 관리 도구 |
| 프런트엔드 | React 18 + Vite, 상태관리 라이브러리 없음, CSS 프레임워크 없음(순수 CSS) |
| 진입점 | `src/main.jsx` (735줄, App·Login·Account·Orders·Settings 등 전부 포함) |
| 분리 컴포넌트 | `src/AIAnalysis.jsx` (545줄) |
| 스타일 | CSS 11개 파일, 총 약 3,100줄. 대부분 한 줄로 압축(minified)되어 있음 |
| 언어 | 전 UI 한국어, `<html lang="ko">` |
| 배포 | PWA (standalone, 세로 고정), 안드로이드 Chrome 설치 사용 |
| 테스트 | `npm test` (vitest, 3개 파일 — 로직 전용이라 시각 회귀는 잡지 못함), `npm run build` |

### 화면 목록 (13개 탭)

일반 사용자: `오늘의 대시보드` `Upbit 추천` `주식 추천` `배당주` `주문 내역` `내 정보`
관리자(ADMIN/MASTER) 추가: `AI 분석` `시스템` `오류` `자동매매` `계산 설정` `사용자` `메일`

모바일(≤760px)에서는 하단 고정 탭바에 4개(`Upbit`/`주식`/`홈`/`AI`)만 노출하고 나머지는 "더보기" 바텀시트로 접는다.

### CSS 임포트 순서 (main.jsx 5~12행) — 캐스케이드가 전적으로 이 순서에 의존한다

```
style.css → sell.css → pwa.css → pagination.css → review.css
→ theme.css → mobile-improvements.css → dashboard.css
```
`AIAnalysis.jsx`가 추가로 `ai.css → ai-chat.css → ai-redesign.css`를 임포트한다.

---

## 2. 핵심 진단: "왜 어두워 보이는가"

사용자가 체감한 "색이 어둡다"는 단순한 취향 문제가 아니라 **세 가지 측정 가능한 결함**의 합이다.

### 2-1. 표면이 서로 분리되지 않는다

WCAG 2.1 SC 1.4.11(비텍스트 대비)은 UI 컴포넌트의 경계에 **3:1**을 요구한다. 현재 값:

| 대상 | 색 조합 | 대비 | 판정 |
|---|---|---|---|
| 페이지 배경 ↔ 카드 | `#0b0d12` ↔ `#141824` | **1.10:1** | 미달 |
| 페이지 배경 ↔ 카드 테두리 | `#0b0d12` ↔ `#202738` | **1.30:1** | 미달 |
| 카드 ↔ 카드 테두리 | `#141824` ↔ `#202738` | **1.19:1** | 미달 |
| 카드 ↔ 내부 가격박스 | `#141824` ↔ `#0f131c` | **1.05:1** | 미달 |
| 카드 ↔ 목표가 진행바 트랙 | `#141824` ↔ `#181f2b` | **1.07:1** | 미달 |
| AI 패널 ↔ AI 카드 | `#11151c` ↔ `#151922` | **1.04:1** | 미달 |

배경의 상대휘도가 `#0b0d12` 기준 **0.40%**, 카드가 **0.93%**다. 즉 화면 전체가 휘도 1% 미만 구간에 뭉쳐 있어 계층이 보이지 않는다. 카드가 "떠 보이지" 않고 전부 한 장의 검은 판처럼 읽힌다.

### 2-2. 작은 글씨 + 저채도 회색 조합이 지각 대비를 무너뜨린다

WCAG 2.x 대비 계산은 **근–검정 영역에서 실제 지각을 과대평가**한다. 같은 4.5:1이라도 배경이 near-black이면 체감 가독성은 훨씬 낮다. 그래서 WCAG 기준으로는 35쌍 중 2쌍만 실패하지만, 지각 기반 알고리즘 **APCA**로 다시 재면 결과가 뒤집힌다.

| 대상 | 크기 | APCA Lc | 필요 Lc | 부족 |
|---|---|---|---|---|
| `.targets-footer-line` (목표 도달률) | 11px | 28.9 | 110 | −81 |
| `.ai-item-delete-btn` (대화 삭제 ✕) | 13px | 32.6 | 95 | −62 |
| `.coin-names small` (보유/매도가능 수량) | 11px | 36.5 | 110 | −74 |
| `.holding-prices-grid small` (현재가·평균가 라벨) | 10px | 36.9 | 120 | −83 |
| `.submetric-item small` (미실현 손익 라벨) | 12px | 37.3 | 100 | −63 |
| `.safety-statement span` (자동매매 상태 설명) | 12px | 39.9 | 100 | −60 |
| `.slide-label` (매도 슬라이더 안내) | 13px | 40.4 | 95 | −55 |
| `.coin-return-badge.up` (수익률 배지) | 11px | 41.9 | 110 | −68 |
| `.hint` / 폼 도움말 | 12px | 42.8 | 100 | −57 |

**검사한 25쌍 중 23쌍이 APCA 기준 미달.** 통과한 것은 `총 평가금액`(34px/700)과 `미실현 손익 금액`(15px/600) 둘뿐이다.

근본 원인은 색상(hue)이 아니라 **10~13px 텍스트가 UI 라벨의 대부분을 차지한다**는 점이다. `font-size` 26종 중 `10px`·`11px`·`12px`가 가장 많이 쓰인다.

### 2-3. 라이트 모드가 아예 없다

`pwa.css`에 `color-scheme: dark`가 고정돼 있고, `prefers-color-scheme` 미디어 쿼리는 전체 CSS에 **0건**이다. 사용자가 밝게 볼 방법이 없다.

---

## 3. 나머지 진단 (구조·접근성·일관성)

### 3-1. 팔레트가 3중으로 충돌한다 — 탭마다 다른 앱처럼 보임

고유 hex 색상 **301개**. 계열이 둘로 갈려 있고 임포트 순서로 덮어쓰기만 해 둔 상태다.

| 계열 | 정의 위치 | 대표 색 | 아직 살아 있는 화면 |
|---|---|---|---|
| **A. 네이비 + 민트** (구) | `style.css`, `pwa.css`, `ai.css`, `ai-chat.css`, `review.css`, `sell.css`, `pagination.css` | 배경 `#07111f`, 강조 `#43e2b1`/`#35d8a6` | 로그인, 사이드바, 추천 카드, 주문 내역, 표 전체, 배당주, 시스템, 오류, 페이지네이션 |
| **B. 슬레이트 + 페리윙클** (신) | `theme.css`, `dashboard.css`, `ai-redesign.css`, `mobile-improvements.css` | 배경 `#0b0d12`, 강조 `#8da2fb` | 오늘의 대시보드, AI 분석 |

구체적 증상:
- 모바일 표 라벨 `td:before`는 민트 `#65dbbc`, 같은 화면 대시보드 배지는 페리윙클 `#8da2fb`.
- 페이저 강조 `b`는 민트 `#63dfbd`, 바로 위 필터칩 활성색은 `#cbd3ff`.
- `.primary` 버튼이 `style.css`에서는 민트-시안 그라디언트, `theme.css`에서는 단색 `#8da2fb`, `ai-redesign.css`에서는 `.ai-page .primary`로 또 한 번 덮어씀.

### 3-2. 같은 의미에 색이 3개

한국 증시 관례(상승=빨강, 하락=파랑)는 올바르게 지키고 있으나 값이 제각각이다.

| 의미 | 값 | 위치 |
|---|---|---|
| 상승/이익 | `#e06c75` | `dashboard.css` `.coin-return-badge.up`, `.profit-pos` |
| 상승/이익 | `#ff7e8e` | `main.jsx` 인라인 `style={{color:...}}` (337행, 343행) |
| 상승/이익 | `#ff7582` | `style.css` `.change.up` |
| 하락/손실 | `#72b0f5` / `#72b2ff` / `#62a9ff` | 각각 dashboard.css / main.jsx 인라인 / style.css |

`main.jsx`에 색 hex가 JS 인라인 스타일로 하드코딩된 지점이 3곳 있다(329, 337, 343행).

### 3-3. 접근성 — 심각도 순

| # | 문제 | 위치 | 위반 기준 |
|---|---|---|---|
| A1 | **키보드로 매도를 실행할 수 없다.** `SlideToConfirm`이 `role="slider"`를 선언했으나 `tabIndex` 없음, `onKeyDown` 없음. 포인터 드래그가 유일한 실행 경로 | `main.jsx` 117~212 | **WCAG 2.1.1 키보드 (Level A)** |
| A2 | **포커스 표시가 전무하다.** 전체 CSS에서 `:focus-visible` **0건**. `button` 요소에 포커스 스타일 정의 없음. `.ai-history-item-btn:focus { outline: none }`으로 명시적 제거까지 함 | `ai-redesign.css:83`, 전역 | **WCAG 2.4.7 (AA)** |
| A3 | **모달 포커스 관리 없음.** `.safe-sell-overlay`는 `role="dialog" aria-modal="true"`만 있고 초기 포커스 이동·Tab 트랩·Escape 닫기·닫은 뒤 포커스 복원이 모두 없다 | `main.jsx` 570~617 | WCAG 2.1.2, 2.4.3 |
| A4 | **터치 타깃 미달.** `.price-freshness summary` 22×22px, `.check input` 18×18px | `mobile-improvements.css`, `style.css` | **WCAG 2.2 SC 2.5.8 (AA, 24×24 최소)** |
| A5 | 터치 타깃 협소(24는 넘으나 권장 44 미달): `.ai-item-delete-btn` 30×30(파괴적 작업), `.safe-sell-close-btn` 32×32, `.dashboard-alert-pill button` ≈23px 높이 | 다수 | HIG/Material 권장 |
| A6 | **제목 레벨 건너뜀.** 헤더 `<h1>` 다음 안전바가 곧바로 `<h4>` | `main.jsx:362` | WCAG 1.3.1 |
| A7 | **대시보드 히어로 영역에 제목이 없다.** 가장 중요한 "총 평가금액" 블록이 heading 없이 `div`+`span`으로만 구성 | `main.jsx` 314~356 | WCAG 1.3.1 |
| A8 | `prefers-reduced-motion` **0건**. `fadeIn`, `modalPop`, `spin`, 모든 `transition`이 무조건 실행 | 전역 | WCAG 2.3.3 (AAA) / 관행 |
| A9 | 네이티브 `alert`/`confirm`/`prompt` 4곳 사용. 스타일 불가, 모바일 UX 파손, 화면 낭독기 맥락 상실 | `AIAnalysis.jsx` 341·345·349·423, `main.jsx:732` | 일관성 |
| A10 | 모바일 탭바가 `span { font-size: 0 }`으로 라벨을 숨김. 접근명은 남지만 취약한 처리 | `pwa.css`, `mobile-improvements.css` | 관행 |

### 3-4. 한글 타이포그래피

- `word-break: keep-all`이 **0건**. 한국어 문장이 어절 중간에서 끊긴다. 경고문·동의문·AI 답변처럼 긴 문장이 많은 앱이라 체감이 크다.
- 반대로 `overflow-wrap: anywhere`가 **20곳 이상** 남용돼 있다. 이건 URL·주문번호처럼 끊어야 하는 값에만 써야 하는데, `.ai-notes ul`, `.ai-setting-list dd`, `.ai-metrics dd`, `.ai-decision` 등 한글 본문에까지 걸려 있어 가독성을 적극적으로 망친다.
- 폰트 스택이 `Inter, Pretendard, "Noto Sans KR", system-ui`인데 **웹폰트 로딩이 없다**. Pretendard가 설치되지 않은 기기에서는 OS 기본 한글 폰트로 떨어져 플랫폼마다 자간·굵기가 달라진다.
- 제목 `letter-spacing`이 `.ai-cockpit h2`(−0.03em), `.hero-valuation`(−0.02em)에만 산발적으로 적용.

### 3-5. 디자인 토큰 부재

| 축 | 고유 값 개수 | 증상 |
|---|---|---|
| 색상 (hex) | **301** | 위 3-1 참조 |
| `border-radius` | **18종** (4·5·6·7·8·9·10·11·12·13·14·16·18·20·22·50%·99px·inherit) | 카드마다 모서리가 미묘하게 다름 |
| `font-size` | **26종** (10~42px + clamp 3종) | 위계가 읽히지 않음 |
| `padding`/`margin`/`gap` | **107종** | 수직 리듬 없음 |

`theme.css`가 `--bg --panel --panel-raised --line --text --muted --accent --positive --danger-color --warning`을 선언하지만, 실제로 `var()`로 소비되는 건 `--line` 정도이고 나머지는 사실상 미사용이다. 변수는 있는데 아무도 안 쓴다.

`z-index`도 1·2·3·5·20·30·999로 관리되지 않는다.

### 3-6. 죽은 CSS

JSX에서 한 번도 참조되지 않는 클래스 (동적 클래스명 오탐 제거 후):

- **`sell.css` 파일 전체** — `.market-sell-button`, `.market-sell-confirm` 등. 매도 UI가 `.safe-sell-modal`로 재작성되면서 통째로 고아가 됨.
- `.account-summary`, `.asset`, `.asset-grid`, `.asset-head`, `.asset-prices`, `.asset-return` — 구 계좌 화면 잔재 (`style.css`, `pwa.css`, `review.css`에 흩어짐)
- `.ai-intro`, `.ai-prose`, `.ai-report` — `.ai-cockpit`/`.ai-markdown`으로 대체됨
- `.ai-history-item` — JSX는 `.ai-history-item-row` / `.ai-history-item-btn`을 쓰는데, 구 스타일이 `ai.css`·`ai-chat.css`·`ai-redesign.css` **3개 파일에 중복**으로 남아 있음
- `.ai-setting-diff` — 비교표로 대체됨
- `.stack`, `.section-title`, `.ask`

### 3-7. 데이터 표현

- `font-variant-numeric: tabular-nums`가 `dashboard.css`에만 적용됐다. `style.css` 쪽 `.price-main strong`, `.change strong`, `.status-card strong`, 표의 모든 `td`, `.dividend > strong`에는 없어서 **30초마다 갱신되는 추천 카드 가격에서 숫자가 흔들린다**.
- 로딩이 전부 스피너(`.loader`) + 텍스트다. 스켈레톤 없음. 대시보드처럼 레이아웃이 확정된 화면은 스켈레톤이 체감 속도에서 유리하다.
- `Empty` 상태는 잘 되어 있으나 액션 버튼이 없다(예: "API 키 등록하러 가기").

### 3-8. PWA 메타 불일치

`index.html`의 `<meta name="theme-color" content="#07111f">`와 `manifest.webmanifest`의 `theme_color`/`background_color`가 **구 네이비 `#07111f`**인데, 실제 `body` 배경은 `theme.css`가 덮어쓴 **`#0b0d12`**다. 설치형 PWA에서 상태바/스플래시와 화면 배경의 색이 어긋난다.

### 3-9. 캐스케이드 취약성

- `pwa.css`의 `aside nav { position: fixed; ... }`가 `.desktop-nav`와 `.mobile-nav` **둘 다** 매치한 뒤, `mobile-improvements.css`가 `aside .desktop-nav { display: none !important }`로 되돌린다. 같은 목적의 하단 탭바 규칙이 두 파일에 중복 선언돼 있다.
- AI 화면의 3개 내부 탭(`판단 요약`/`AI 대화`/`근거·설정`)은 `.ai-view-summary .ai-first-question, ... { display: none !important }` 식의 긴 선택자 나열로 구현돼 있다(`ai-redesign.css` 150~161행). 새 섹션을 추가할 때마다 이 목록을 손으로 갱신해야 해서 깨지기 쉽다.

---

## 4. 수정 사항

> **전제: 기능·문구·API 호출은 바꾸지 않는다.** 이 앱은 실제 자금을 다루므로 아래는 **전부 금지**다.
> - `api()` 호출 경로·페이로드·메서드 변경
> - 매도/자동매매/설정 적용의 권한 조건(MASTER 게이팅), 동의 체크박스, 2단계 확인 절차 제거·완화
> - 면책·경고·안전 안내 문구의 삭제나 의미 변경 (줄바꿈·서식 조정은 허용)
> - `useEffect` 폴링 주기, 요청 취소(`createRequestGate`) 로직
> - 백엔드 파일(`api-service/app`, `calculation-service`) 일체

### P0 — 반드시 처리 (기반 작업 + 치명적 접근성)

**P0-1. 3티어 디자인 토큰 도입**

`src/tokens.css` 신설. 다른 모든 CSS보다 먼저 임포트.

```
primitive  →  semantic  →  component
--gray-900    --surface-page      --card-bg
--blue-400    --text-primary      --btn-primary-bg
```

- **primitive**: 중립 12단계(0~1000) + 브랜드/상승/하락/경고/성공 각 5단계. 순검정(`#000`)·순백(`#fff`)은 배경에 쓰지 않는다.
- **semantic**: `--surface-page`, `--surface-raised`, `--surface-sunken`, `--surface-overlay`, `--border-subtle`, `--border-strong`, `--text-primary`, `--text-secondary`, `--text-tertiary`, `--text-disabled`, `--accent`, `--price-up`, `--price-down`, `--state-success/warning/danger/info`, `--focus-ring`
- **component**: 필요한 곳에서만. 컴포넌트 토큰이 primitive를 직접 참조하면 안 된다(반드시 semantic 경유).
- 간격은 4px 배수 스케일 `--space-1`(4) ~ `--space-12`(64)로 통일.
- 반경은 `--radius-sm`(6) / `--radius-md`(10) / `--radius-lg`(14) / `--radius-xl`(18) / `--radius-full`(999) **5종만**.
- 타이포는 `--text-xs`(12) `--text-sm`(13) `--text-base`(14) `--text-md`(16) `--text-lg`(18) `--text-xl`(22) `--text-2xl`(28) `--text-3xl`(clamp) **8종만**. **10px·11px는 스케일에서 제외한다.**
- `--z-base`(0) `--z-sticky`(10) `--z-nav`(20) `--z-overlay`(50) `--z-modal`(60) `--z-toast`(70)

**P0-2. 라이트 / 다크 테마 양립**

- `:root`에 라이트 팔레트를 기본값으로 정의한다.
- `@media (prefers-color-scheme: dark)`를 `:root:not([data-theme="light"])`로 감싸 다크 값을 재정의한다.
- `:root[data-theme="dark"]`에도 같은 다크 값을 정의해 수동 토글이 양방향으로 이긴다.
- 헤더에 3단 토글(`시스템` / `라이트` / `다크`)을 추가하고 선택값을 `localStorage`에 저장한다. **접근은 반드시 `try/catch`로 감싼다**(프라이빗 모드·사이트 데이터 차단 시 throw).
- 초기 로드 깜빡임(FOUC) 방지: `index.html`의 `<head>`에 저장값을 읽어 `<html data-theme>`를 세팅하는 동기 인라인 스크립트를 둔다.
- **어떤 색도 미디어 쿼리나 `[data-theme]` 블록 안에서만 정의되면 안 된다.** 모든 색은 bare `:root`에 기본값이 있어야 한다.

**P0-3. 다크 테마 표면 계단 재설계**

- 페이지 배경을 `#0b0d12`(휘도 0.40%)에서 **`#13161c`~`#161a21` 대역**으로 올린다.
- 표면 단계를 **최소 4단**(page < sunken < raised < overlay)으로 두고, **인접 단계 간 대비 ≥ 1.25:1**, **모든 컴포넌트 경계(테두리 또는 표면 차)는 배경 대비 ≥ 3:1**을 만족시킨다.
- 테두리에만 의존하지 말고 표면 밝기 차이로도 계층을 만든다(다크 모드의 표준 접근: 높을수록 밝게).
- 강조색은 채도를 낮춘다(다크에서 고채도는 halation 유발). 브랜드 `#8da2fb`는 유지하되 배경 채색(`rgba(...,0.12)`)은 표면 토큰으로 대체.

**P0-4. 라이트 테마 신설**

- 배경 `#f7f8fa`대, 카드 `#ffffff`, 테두리 `#e3e6ec`대.
- **순백 배경에 순검정 텍스트 조합은 피한다**(`#1a1d23` 수준의 잉크색 사용).
- 상승 빨강·하락 파랑은 라이트에서 명도를 낮춰 재정의한다(다크용 파스텔 톤을 그대로 쓰면 흰 배경에서 대비 미달).

**P0-5. 텍스트 크기·대비 정상화**

- **10px·11px 텍스트를 전부 제거**한다. 최소 12px, 본문은 14px 이상.
- 보조 텍스트 색을 `--text-secondary`/`--text-tertiary`로 통일하고, 아래 5장 기준을 만족하도록 명도를 올린다.
- `.hero-label`, `.coin-names small`, `.holding-prices-grid small`, `.targets-footer-line`, `.ai-meta-text`, `.submetric-item small`, `.hint`, `.ai-cockpit-stats small`, `.eyebrow` 등이 주요 대상.

**P0-6. 포커스 표시 전면 도입** (WCAG 2.4.7)

```css
:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
  border-radius: inherit;
}
```
- `ai-redesign.css:83`의 `.ai-history-item-btn:focus { outline: none }`을 **삭제**한다.
- `style.css`의 `.form input { outline: none }`은 `:focus-visible` 규칙으로 대체한다.
- 포커스 링은 라이트/다크 양쪽에서 인접 배경 대비 **≥ 3:1**이어야 한다.
- 하단 고정 탭바·sticky 입력창이 포커스된 요소를 가리지 않게 한다(WCAG 2.2 SC 2.4.11). 스크롤 컨테이너에 `scroll-padding-bottom`을 준다.

**P0-7. 슬라이드 매도의 키보드 대체 경로** (WCAG 2.1.1, Level A — 가장 심각)

`SlideToConfirm`에:
- `tabIndex={0}` 부여
- `onKeyDown` 처리: `←/→`로 5%씩, `Home`/`End`로 0/100%, 90% 이상에서 `Enter` 또는 `Space`로 확정
- `aria-valuetext`로 현재 상태를 한국어로 안내 (예: `"48퍼센트 — 끝까지 밀면 매도됩니다"`)
- **오작동 방지라는 원래 목적을 훼손하지 말 것.** 단일 키 입력으로 즉시 체결되면 안 된다. `←/→`를 여러 번 눌러 90%에 도달한 뒤 별도의 확정 키를 눌러야 실행되게 한다.
- 슬라이더 옆에 대체 수단(예: "키보드로 확인" 토글 → 문구 입력 확인)을 두는 것도 허용한다. 단계 수는 줄이지 않는다.

**P0-8. 모달 포커스 관리**

`.safe-sell-overlay` / `.safe-sell-modal`에:
- 열릴 때 첫 번째 의미 있는 컨트롤로 포커스 이동
- Tab/Shift+Tab을 모달 내부로 순환(포커스 트랩)
- `Escape`로 닫기 (단, `selling` 중에는 무시 — 현재 오버레이 클릭 동작과 동일한 규칙)
- 닫을 때 열었던 버튼으로 포커스 복원
- `aria-labelledby`로 제목과 연결 (현재는 `aria-label` 문자열)
- 배경 스크롤 잠금

**P0-9. 터치 타깃 최소 24×24 보장** (WCAG 2.2 SC 2.5.8)

- `.price-freshness summary` 22×22 → **최소 24, 권장 32**
- `.check input` 18×18 → **최소 24** (동의 체크박스이므로 중요)
- `.dashboard-alert-pill button` → 높이 최소 24
- 파괴적/빈번 작업은 44×44 권장: `.ai-item-delete-btn`(30), `.safe-sell-close-btn`(32), 모바일 탭바 버튼

### P1 — 일관성과 구조

**P1-1. 팔레트 통일**
- 계열 A(민트-네이비)를 **완전히 제거**하고 계열 B(슬레이트-페리윙클)로 수렴시킨다. 로그인·사이드바·추천 카드·주문 내역·표·배당주·시스템·오류·페이저 전부.
- 목표: 고유 hex 색상 **301 → 40 이하**(토큰 정의부 제외 시 0에 수렴).
- `main.jsx` 329·337·343행의 인라인 hex를 CSS 클래스로 옮긴다.

**P1-2. 상승/하락 색 단일화 + 비색상 단서**
- `--price-up` / `--price-down` 각 1개 값으로 통일. **한국 증시 관례(상승=빨강, 하락=파랑)는 반드시 유지**한다.
- 색에만 의존하지 않도록 `▲`/`▼` 또는 부호를 항상 동반시킨다(현재 `+`/`−` 부호는 대체로 있으나 `.coin-return-badge`, `.hero-pnl-pill` 등에서 일관성 확인 필요).

**P1-3. 죽은 CSS 제거**
- `sell.css` 파일 삭제 + `main.jsx`의 임포트 제거
- `.account-summary`, `.asset*` 6종, `.ai-intro`, `.ai-prose`, `.ai-report`, `.ai-setting-diff`, `.stack`, `.section-title`, `.ask` 제거
- `.ai-history-item` 중복 정의 3곳을 `.ai-history-item-row`/`-btn` 하나로 정리
- `aside nav` 하단 탭바 규칙이 `pwa.css`와 `mobile-improvements.css`에 이중으로 있는 것을 한 곳으로 합침

**P1-4. CSS 파일 재편**

11개 패치 레이어를 역할별로 정리한다. 권장 구성:
```
tokens.css      디자인 토큰 (primitive/semantic, 라이트·다크)
base.css        리셋, 타이포, 폼, 버튼, 포커스
layout.css      레이아웃, 사이드바, 헤더, 모바일 내비
components.css  카드, 배지, 표, 모달, 페이저, 빈 상태, 스켈레톤
dashboard.css   오늘의 대시보드
ai.css          AI 분석
```
- **임포트 순서에 의존한 덮어쓰기를 없앤다.** 같은 속성을 두 파일이 서로 덮어쓰는 구조를 만들지 않는다.
- `!important`는 제3자 스타일 회피 목적이 아닌 한 사용 금지. 현재 `.check`, `.krw-badge`, `.highlight-krw`, AI 뷰 전환부 등에 남아 있다.
- 압축 CSS를 **정상 포맷(들여쓰기·줄바꿈)으로 푼다.** 유지보수가 불가능한 상태다.

**P1-5. 한글 타이포그래피**
- 본문·설명·경고문에 `word-break: keep-all` 적용. 가능하면 `text-wrap: pretty`도.
- `overflow-wrap: anywhere`는 **주문번호(`.order-foot code`), URL, 종목코드에만** 남기고 한글 본문에서 전부 제거.
- 웹폰트를 `fonts.googleapis.com` 또는 self-host로 실제 로딩하거나, 로딩하지 않을 거면 폰트 스택에서 설치되지 않은 이름을 빼고 `system-ui` 기반으로 정직하게 정리한다. 어느 쪽이든 플랫폼 간 렌더링을 예측 가능하게 만든다.
- 한글 제목: `line-height` 1.3~1.4, `letter-spacing` −0.02em 수준으로 통일. 본문은 `line-height` 1.6~1.75.

**P1-6. 숫자 표현**
- 가격·수량·수익률·금액을 표시하는 **모든** 요소에 `font-variant-numeric: tabular-nums` 적용. 누락 지점: `.price-main strong`, `.change strong`, `.status-card strong`, `.dividend > strong`, 표의 `td`, `.order-values span`, `.ai-metrics dd`.
- 30초 주기로 갱신되는 추천 카드 가격이 흔들리지 않는지 확인.

**P1-7. 제목 구조 정리**
- `h1`(페이지 제목) → `h2`(섹션) → `h3`(카드) 순서로 레벨 건너뜀 제거. `main.jsx:362`의 `<h4>`가 대표 사례.
- 대시보드 히어로 카드에 시각적으로는 라벨처럼 보이되 의미상 `h2`인 제목을 부여한다.
- 각 `section`에 `aria-labelledby` 또는 `aria-label` 부여.

**P1-8. 네이티브 다이얼로그 교체**
- `AIAnalysis.jsx`의 `window.alert` 2곳 → 인라인 알림 배너(`.notice`/`.error`)
- `window.confirm` 2곳 → 기존 `.safe-sell-modal` 패턴을 재사용한 공용 확인 모달 컴포넌트
- `main.jsx:732`의 `prompt()` → 인라인 폼
- **확인 단계의 수와 문구의 강도를 낮추지 말 것.** 표현 수단만 바꾼다.

**P1-9. 모션 접근성**
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```
- `chatBottomRef.scrollIntoView({behavior: 'smooth'})`도 이 설정을 존중하게 한다.
- 로딩 스피너는 예외로 두되 회전 속도를 낮춘다.

**P1-10. PWA 메타 동기화**
- `index.html`의 `theme-color`를 라이트/다크 각각 `media` 속성으로 2개 선언.
- `manifest.webmanifest`의 `theme_color`/`background_color`를 새 팔레트에 맞춘다.

### P2 — 체감 품질

**P2-1. 스켈레톤 로딩**
- 대시보드, 추천 카드, 주문 내역, AI 대화 목록처럼 레이아웃이 확정된 화면에 스켈레톤을 도입한다.
- 스피너는 저장·인증·주문 같은 짧은 단발 동작에만 남긴다.
- **400ms 미만이면 아무것도 띄우지 않는다**(깜빡임이 더 나쁘다).
- 스켈레톤에 `aria-hidden="true"` + 별도의 `role="status"` 텍스트.

**P2-2. 정보 위계 재조정 (점진적 공개)**
- 대시보드: 1순위 총 평가금액·오늘 변동 / 2순위 자동매매 안전 상태 / 3순위 보유 자산 / 4순위 오늘 체결. 현재 순서는 타당하니 **시각적 위계(크기·여백·표면 단계)를 이 순서에 맞춘다.**
- AI 분석 화면의 3중 탭(`판단 요약`/`AI 대화`/`근거·설정`)은 정보량이 많아 유지가 타당하다. 다만 `display:none !important` 나열을 `data-view` 속성 기반의 짧은 선택자로 바꿔 유지보수성을 확보한다.
- 보유 종목 카드에 정보 밀도가 높다(현재가·평균가·평가손익·손절·목표·진행률·AI 판단·버튼 2개). 2차 정보는 접기(`details`)로 내린다.

**P2-3. 빈 상태에 행동 유도**
- `Empty` 컴포넌트에 선택적 액션 버튼 prop을 추가한다(예: API 키 미등록 → "API 키 등록", 대화 없음 → "새 분석 시작").

**P2-4. 사이드바 정보 구조**
- 13개 탭이 일반 기능과 관리 기능을 평평하게 나열한다. `투자`(추천·배당·주문) / `내 계좌`(대시보드·내 정보) / `AI` / `관리`(시스템·오류·자동매매·설정·사용자·메일) 정도로 그룹 라벨을 넣는다.
- 모바일 "더보기" 바텀시트에도 같은 그룹을 반영한다.

**P2-5. 표 반응형**
- `pwa.css`의 `table → block` 카드 변환은 잘 작동한다. 다만 `td:before`의 색과 크기를 새 토큰으로 맞추고, 라벨 열 너비 `minmax(90px, 36%)`를 한글 라벨 길이에 맞게 재조정한다.

---

## 5. 검수 기준 (Acceptance Criteria)

각 항목은 **통과/실패를 판정할 수 있어야** 한다. 에이전트는 매 루프마다 아래 전부를 검사하고 결과표를 출력한다.

### 5-A. 자동 검증 (스크립트로 판정)

저장소에 `scripts/ui-audit.mjs`를 만들어 아래를 검사하고, 실패 시 0이 아닌 종료 코드를 반환하게 한다.

| ID | 기준 | 임계값 |
|---|---|---|
| **AUTO-1** | `npm run build` 성공 | 오류 0 |
| **AUTO-2** | `npm test` 전부 통과 | 실패 0 |
| **AUTO-3** | CSS 내 고유 hex 색상 수 (`tokens.css` 제외) | **≤ 10** |
| **AUTO-4** | `tokens.css` 내 primitive 색상 수 | ≤ 60 |
| **AUTO-5** | 고유 `border-radius` 값 (`inherit`/`50%`/`99px` 제외) | **≤ 5** |
| **AUTO-6** | 고유 `font-size` 값 (`clamp()` 제외) | **≤ 8** |
| **AUTO-7** | `font-size`가 12px 미만인 선언 | **0건** |
| **AUTO-8** | `:focus-visible` 규칙 존재 | ≥ 1, 전역 버튼 커버 |
| **AUTO-9** | `outline: none` / `outline: 0` 선언 | **0건** (`:focus-visible` 대체 규칙이 같은 선택자에 있는 경우만 예외) |
| **AUTO-10** | `@media (prefers-reduced-motion: reduce)` 블록 | ≥ 1 |
| **AUTO-11** | 라이트/다크 양쪽 정의 존재 | `:root` 기본 + `prefers-color-scheme: dark` + `[data-theme="dark"]` + `[data-theme="light"]` |
| **AUTO-12** | `!important` 선언 수 | **≤ 3** (사유를 주석으로 명시한 것만) |
| **AUTO-13** | JSX 인라인 `style={{color:` 내 hex 리터럴 | **0건** |
| **AUTO-14** | JSX에서 참조되지 않는 CSS 클래스 | **≤ 5** (동적 클래스명은 화이트리스트) |
| **AUTO-15** | `window.alert` / `window.confirm` / `prompt(` 호출 | **0건** |
| **AUTO-16** | `index.html` `theme-color` ↔ `manifest.webmanifest` `theme_color` ↔ 실제 `--surface-page` 값 | 일치 |
| **AUTO-17** | WCAG 2.x 대비: 모든 텍스트/배경 쌍 | **≥ 4.5:1** (18.66px+bold 또는 24px+ 는 3:1) |
| **AUTO-18** | WCAG 1.4.11: 컴포넌트 경계 ↔ 인접 배경 | **≥ 3:1** |
| **AUTO-19** | **APCA Lc**: 모든 텍스트 쌍, 폰트 크기·굵기 반영 | 12px→Lc 100 / 14px→Lc 90 / 16px→Lc 75 / 18px→Lc 75 / 24px+→Lc 60 |
| **AUTO-20** | 인접 표면 단계 간 대비 | **≥ 1.25:1** |
| **AUTO-21** | 위 17~20을 **라이트·다크 양쪽**에서 검사 | 양쪽 모두 통과 |

> **AUTO-19가 이 작업의 핵심 게이트다.** 현재 25쌍 중 23쌍 미달 → 목표 0쌍 미달.
> APCA 구현은 W3 APCA 0.1.9 (`mainTRC=2.4`, `Rco/Gco/Bco = 0.2126729/0.7151522/0.0721750`, `blkThrs=0.022`, `blkClmp=1.414`, `scale=1.14`, `normBG=0.56 normTXT=0.57 revTXT=0.62 revBG=0.65`, `loOffset=0.027`, `loClip=0.1`, `deltaYmin=0.0005`)를 쓴다.

### 5-B. 수동 검증 (에이전트가 실제로 렌더링해 확인)

브라우저를 띄워 확인하고, 각 항목에 대해 **무엇을 어떻게 확인했는지 한 줄씩 기록**한다.

**뷰포트 3종 × 테마 2종 = 6조합**에서 모든 화면을 확인한다: `360×740`(모바일), `768×1024`(태블릿), `1440×900`(데스크톱) × 라이트/다크.

| ID | 기준 |
|---|---|
| **M-1** | 6조합 전부에서 **가로 스크롤이 발생하지 않는다** (`document.scrollingElement.scrollWidth <= clientWidth`) |
| **M-2** | 6조합 전부에서 텍스트 잘림·요소 겹침이 없다 |
| **M-3** | 360px에서 좌우 여백이 최소 16px 유지된다 |
| **M-4** | 모바일에서 하단 고정 탭바가 **어떤 콘텐츠도 가리지 않는다** (AI 메시지 입력창, 페이저, 마지막 카드, 모달 취소 버튼) |
| **M-5** | 13개 탭 전체를 순회했을 때 **동일한 시각 언어**를 유지한다 (배경·카드·버튼·배지·표가 탭마다 달라 보이지 않음) |
| **M-6** | Tab 키만으로 모든 대화형 요소에 도달할 수 있고, **매 순간 포커스 위치가 눈에 보인다** |
| **M-7** | Tab 순서가 시각적 순서와 일치한다 |
| **M-8** | 매도 모달: Tab이 모달 밖으로 나가지 않는다 / Escape로 닫힌다 / 닫은 뒤 원래 버튼에 포커스가 돌아온다 |
| **M-9** | **키보드만으로 매도 슬라이더를 끝까지 조작해 확정할 수 있다.** 동시에 단일 키 입력으로는 절대 체결되지 않는다 |
| **M-10** | OS 다크 설정을 바꾸면 테마가 따라간다. 수동 토글은 OS 설정을 이긴다. 새로고침 후에도 선택이 유지된다 |
| **M-11** | 테마 전환 시 FOUC(흰 화면 번쩍임)가 없다 |
| **M-12** | OS "동작 줄이기"를 켜면 애니메이션·부드러운 스크롤이 멈춘다 |
| **M-13** | 브라우저 확대 200%에서 콘텐츠 손실·겹침이 없다 (WCAG 1.4.4) |
| **M-14** | 한글 문장이 어절 중간에서 끊기지 않는다. 특히 경고문·동의문·AI 답변 |
| **M-15** | 30초 갱신되는 추천 카드 가격에서 **숫자가 좌우로 흔들리지 않는다** |
| **M-16** | 상승/하락이 색 없이도(흑백 스크린샷) 구분된다 |
| **M-17** | 상승=빨강, 하락=파랑 한국 관례가 전 화면에서 유지된다 |
| **M-18** | 로딩 → 데이터 표시 전환 시 레이아웃 점프(CLS)가 없다 |
| **M-19** | 빈 상태·오류 상태·로딩 상태가 6조합 전부에서 정상 표시된다 |
| **M-20** | 설치형 PWA에서 상태바 색이 화면 배경과 이어진다 |

### 5-C. 회귀 방지 (기능 불변 확인)

| ID | 기준 |
|---|---|
| **R-1** | 매도 확인 단계 수가 이전과 동일하다 (모달 → 슬라이드 90% → 확정) |
| **R-2** | MASTER 권한 게이팅이 모든 지점에서 그대로다 (매도 버튼, 설정 적용, 자동 판단) |
| **R-3** | 모든 동의 체크박스가 그대로 존재하고 기본값이 꺼짐이다 |
| **R-4** | 면책·경고 문구가 하나도 삭제되지 않았다 (문자열 diff로 확인) |
| **R-5** | `api()` 호출의 경로·메서드·바디가 변경되지 않았다 (grep diff) |
| **R-6** | 적용된 분석 기록의 삭제 차단(`applied_candidate_id`), 진행 중 분석 삭제 차단이 유지된다 |
| **R-7** | 폴링 주기(추천 30초, AI 상세 3초, 가격 신선도 15초)가 변경되지 않았다 |
| **R-8** | 백엔드 파일이 하나도 수정되지 않았다 (`git diff --stat`로 확인) |

---

## 6. 루프 프로토콜

```
[0] 기준선 측정
    └ 감사 스크립트 작성 → 현재 상태 측정 → baseline.json 저장

[1] 계획
    └ P0 → P1 → P2 순. 한 번에 한 덩어리(P0-1처럼 번호 단위)만 건드린다.

[2] 수정
    └ 커밋 단위 = 지시서의 번호 하나. 커밋 메시지에 번호를 적는다.

[3] 검토
    ├ 5-A 자동 검사 전체 실행 → 결과표
    ├ 5-B 수동 검사: 6조합 렌더링, 각 항목 확인 근거 1줄씩
    └ 5-C 회귀 검사

[4] 판정
    ├ 전부 통과 → 다음 항목으로 (P2까지 끝났으면 [5])
    ├ 실패 있음 → 실패 원인을 적고 [2]로
    └ 같은 항목에서 3회 연속 실패 → 수정을 멈추고, 무엇이 왜 막히는지
                                    (충돌하는 기준, 불가능한 제약)을 보고한다

[5] 종료
    └ 종료 조건을 전부 만족했을 때만 완료 선언
```

### 종료 조건 (전부 만족해야 함)

1. 5-A의 AUTO-1 ~ AUTO-21 **전부 통과**
2. 5-B의 M-1 ~ M-20 **전부 통과**, 각 항목에 확인 근거가 기록됨
3. 5-C의 R-1 ~ R-8 **전부 통과**
4. 라이트·다크 양쪽에서 13개 탭 전체 스크린샷이 있고, 시각 언어가 일관됨
5. 변경 요약: 무엇을 왜 바꿨는지 + 남은 알려진 제약

### 매 루프 보고 형식

```
## 루프 N — 대상: P0-3 (다크 표면 계단)

### 변경
- (파일:범위) 무엇을 왜

### 자동 검사
| ID | 기준 | 이전 | 현재 | 판정 |
|----|------|------|------|------|
| AUTO-3 | 고유 hex ≤10 | 301 | 46 | 실패 |
...

### 수동 검사
- M-1 가로 스크롤: 6조합 확인, scrollWidth/clientWidth 동일 — 통과
- M-4 탭바 가림: 360px 다크에서 AI 입력창이 8px 겹침 — 실패
...

### 회귀
- R-4 문구 diff: 삭제 0건, 줄바꿈 변경 3건 — 통과
...

### 다음 루프에서 할 것
- M-4 실패 원인: .ai-message-composer bottom 계산이 새 탭바 높이를 반영 안 함
```

---

## 7. Antigravity에 붙여 넣을 프롬프트

> 아래 블록 전체를 복사해서 전달한다. `docs/ui-redesign-brief-2026-09-23.md`(이 문서)도 저장소에 함께 있으므로, 에이전트가 4·5장을 직접 읽게 하면 프롬프트를 더 줄일 수 있다.

```text
너는 시니어 프로덕트 디자이너이자 프런트엔드 엔지니어다.
대상 저장소의 `api-service/frontend` UI를 개선하되, 아래 규칙을 엄격히 따른다.

## 대상
- React 18 + Vite, CSS 프레임워크 없음(순수 CSS 11개 파일, 대부분 한 줄로 압축됨)
- 진입점 `src/main.jsx`(735줄), 분리 컴포넌트 `src/AIAnalysis.jsx`(545줄)
- 전 UI 한국어, PWA(standalone), 13개 탭
- 성격: 실제 자금을 다루는 주식·암호화폐 자동매매 관리 도구

## 배경 — 이미 측정된 사실
1. 팔레트가 3중으로 충돌한다. 고유 hex 색상 301개.
   - 구: 네이비+민트 (style.css, pwa.css, ai.css, ai-chat.css, review.css, sell.css, pagination.css)
   - 신: 슬레이트+페리윙클 (theme.css, dashboard.css, ai-redesign.css, mobile-improvements.css)
   - 결과: 탭을 옮기면 다른 앱처럼 보인다.
2. 다크 표면이 분리되지 않는다. 배경↔카드 1.10:1, 카드↔테두리 1.19:1
   (WCAG 1.4.11 기준 3:1). 배경 상대휘도 0.40%, 카드 0.93%.
3. 10~13px 저채도 회색 텍스트가 UI 라벨 대부분을 차지한다.
   APCA로 재면 검사한 25쌍 중 23쌍이 기준 미달이다.
   (WCAG 2.x는 near-black에서 지각을 과대평가하므로 APCA를 기준으로 삼는다)
4. 라이트 모드가 없다. prefers-color-scheme 0건, color-scheme:dark 고정.
5. :focus-visible 0건. 버튼에 포커스 표시가 전혀 없고 outline:none이 2곳 있다.
6. 매도 슬라이더가 포인터 전용이라 키보드로 매도할 수 없다 (WCAG 2.1.1 Level A 위반).
7. 매도 모달에 포커스 트랩·Escape·포커스 복원이 전부 없다.
8. 터치 타깃 미달: .price-freshness summary 22px, .check input 18px (WCAG 2.2 SC 2.5.8은 24px).
9. 죽은 CSS: sell.css 전체, .asset* 6종, .ai-intro/.ai-prose/.ai-report/.ai-history-item 등.
10. 한글 word-break:keep-all 0건, 반대로 overflow-wrap:anywhere가 한글 본문에 20곳 넘게 남용됨.
11. tabular-nums가 일부에만 적용돼 30초마다 갱신되는 가격 숫자가 흔들린다.
12. 토큰 부재: border-radius 18종, font-size 26종, spacing 107종, z-index 7종 무관리.
13. PWA theme_color(#07111f)가 실제 배경(#0b0d12)과 불일치.
14. 네이티브 alert/confirm/prompt 4곳 사용.

## 목표
"색이 어둡고 답답하다"를 해결한다. 단, 이건 색조 문제가 아니라
(a) 표면 계층이 안 보이고 (b) 글씨가 작고 흐리고 (c) 라이트 모드가 없어서다.
세 가지를 전부 해결한다.

## 금지 사항 — 위반 시 작업 무효
- api() 호출 경로·메서드·페이로드 변경 금지
- 매도/자동매매/설정 적용의 권한 조건(MASTER 게이팅) 제거·완화 금지
- 동의 체크박스, 2단계 확인 절차의 단계 수 축소 금지
- 면책·경고·안전 안내 문구의 삭제나 의미 변경 금지 (줄바꿈·서식 조정만 허용)
- 폴링 주기, 요청 취소 로직(createRequestGate) 변경 금지
- 백엔드(api-service/app, calculation-service) 수정 금지
- 상승=빨강 / 하락=파랑 한국 증시 관례를 뒤집지 말 것
- CSS 프레임워크(Tailwind 등) 도입 금지. 순수 CSS 유지.

## 작업 순서

### P0 (반드시)
P0-1 3티어 디자인 토큰 도입 (primitive → semantic → component).
     src/tokens.css 신설, 가장 먼저 임포트. component가 primitive를 직접
     참조하면 안 된다. 간격 4px 배수, 반경 5종, 타이포 8종(10px·11px 제외),
     z-index 6단계.
P0-2 라이트/다크 양립. :root에 라이트 기본값 → @media(prefers-color-scheme:dark)를
     :root:not([data-theme="light"])로 감싸 다크 재정의 → :root[data-theme="dark"]에도
     동일 정의(수동 토글이 양방향으로 이기게). 헤더에 3단 토글(시스템/라이트/다크),
     localStorage 저장은 반드시 try/catch. index.html head에 동기 인라인 스크립트로
     FOUC 방지. 어떤 색도 미디어쿼리 안에서만 정의되면 안 된다.
P0-3 다크 표면 계단 재설계. 페이지 배경을 #13161c~#161a21 대역으로 올리고
     표면 4단(page<sunken<raised<overlay), 인접 단계 대비 ≥1.25:1,
     컴포넌트 경계는 배경 대비 ≥3:1. 강조색 채도를 낮춰 halation 방지.
P0-4 라이트 테마 신설. 배경 #f7f8fa대, 카드 #fff, 잉크 #1a1d23대.
     순백+순검정 조합 회피. 상승/하락 색을 라이트용으로 재정의.
P0-5 10px·11px 텍스트 전면 제거(최소 12px, 본문 14px+). 보조 텍스트 명도 상향.
P0-6 :focus-visible 전역 도입(outline 2px + offset 2px, 배경 대비 ≥3:1).
     ai-redesign.css:83의 outline:none 삭제. 하단 고정 탭바가 포커스된 요소를
     가리지 않게 scroll-padding 처리(WCAG 2.2 SC 2.4.11).
P0-7 SlideToConfirm 키보드 대체 경로. tabIndex=0, ←/→ 5%씩, Home/End,
     90% 이상에서 Enter/Space로 확정, aria-valuetext 한국어 안내.
     ★ 단일 키 입력으로 즉시 체결되면 절대 안 된다. 오작동 방지라는
     원래 목적을 반드시 보존할 것.
P0-8 매도 모달 포커스 관리: 초기 포커스, 포커스 트랩, Escape 닫기(selling 중 제외),
     닫은 뒤 트리거로 포커스 복원, aria-labelledby, 배경 스크롤 잠금.
P0-9 터치 타깃 최소 24×24 (파괴적 작업은 44×44 권장).

### P1 (일관성)
P1-1 팔레트 통일 — 민트-네이비 계열 완전 제거. 고유 hex 301 → 10 이하.
     main.jsx 329·337·343행 인라인 hex를 클래스로 이동.
P1-2 상승/하락 색 각 1개로 통일 + ▲▼ 또는 부호로 비색상 단서 병행.
P1-3 죽은 CSS 제거 (sell.css 파일 삭제 포함).
P1-4 CSS 재편: tokens / base / layout / components / dashboard / ai 6개 파일.
     임포트 순서 의존 덮어쓰기 제거. !important 3개 이하.
     압축된 CSS를 정상 포맷으로 풀 것.
P1-5 한글 타이포: 본문에 word-break:keep-all, overflow-wrap:anywhere는
     주문번호/URL/종목코드에만. 웹폰트를 실제로 로딩하거나 스택을 정직하게 정리.
     제목 line-height 1.3~1.4 / letter-spacing -0.02em, 본문 1.6~1.75.
P1-6 가격·수량·수익률 표시 요소 전부에 font-variant-numeric: tabular-nums.
P1-7 제목 레벨 건너뜀 제거(main.jsx:362 h4). 히어로 카드에 h2 부여.
     각 section에 aria-labelledby.
P1-8 alert/confirm/prompt 4곳을 인라인 배너·공용 확인 모달·인라인 폼으로 교체.
     ★ 확인 단계 수와 경고 강도는 그대로.
P1-9 @media (prefers-reduced-motion: reduce) 추가. scrollIntoView도 존중.
P1-10 index.html theme-color(라이트/다크 2개) + manifest theme_color 동기화.

### P2 (체감 품질)
P2-1 스켈레톤 로딩(대시보드·추천·주문·AI 목록). 400ms 미만이면 아무것도 안 띄움.
     스켈레톤에 aria-hidden + 별도 role="status" 텍스트.
P2-2 정보 위계를 시각 위계(크기·여백·표면 단계)로 반영.
     AI 화면의 display:none !important 나열을 data-view 속성 기반으로 교체.
     보유 카드의 2차 정보는 details로 접기.
P2-3 Empty 컴포넌트에 액션 버튼 prop 추가.
P2-4 사이드바 13개 탭에 그룹 라벨(투자/내 계좌/AI/관리). 모바일 바텀시트에도 반영.
P2-5 모바일 표 카드 변환의 라벨 색·너비를 새 토큰에 맞춤.

## 검수 — 매 루프마다 전부 검사하고 결과표를 출력한다

먼저 scripts/ui-audit.mjs를 만들어 아래를 자동 검사하게 한다
(실패 시 non-zero exit).

AUTO-1  npm run build 성공
AUTO-2  npm test 전부 통과
AUTO-3  CSS 고유 hex 색상 수(tokens.css 제외) ≤ 10
AUTO-4  tokens.css primitive 색상 ≤ 60
AUTO-5  고유 border-radius(inherit/50%/99px 제외) ≤ 5
AUTO-6  고유 font-size(clamp 제외) ≤ 8
AUTO-7  font-size < 12px 선언 0건
AUTO-8  :focus-visible 규칙 존재, 전역 버튼 커버
AUTO-9  outline:none / outline:0 선언 0건
AUTO-10 prefers-reduced-motion 블록 ≥ 1
AUTO-11 :root 기본 + prefers-color-scheme:dark + [data-theme=dark] + [data-theme=light] 모두 존재
AUTO-12 !important ≤ 3 (사유 주석 필수)
AUTO-13 JSX 인라인 style에 hex 리터럴 0건
AUTO-14 미참조 CSS 클래스 ≤ 5 (동적 클래스는 화이트리스트)
AUTO-15 window.alert / window.confirm / prompt( 0건
AUTO-16 index.html theme-color ↔ manifest theme_color ↔ --surface-page 일치
AUTO-17 WCAG 2.x: 모든 텍스트/배경 쌍 ≥ 4.5:1 (대형 텍스트 3:1)
AUTO-18 WCAG 1.4.11: 컴포넌트 경계 ↔ 인접 배경 ≥ 3:1
AUTO-19 ★ APCA Lc (핵심 게이트):
        12px→Lc 100 / 14px→Lc 90 / 16px→Lc 75 / 18px→Lc 75 / 24px+→Lc 60
        APCA 0.1.9 (mainTRC=2.4, Rco/Gco/Bco=0.2126729/0.7151522/0.0721750,
        blkThrs=0.022, blkClmp=1.414, scale=1.14,
        normBG=0.56 normTXT=0.57 revTXT=0.62 revBG=0.65,
        loOffset=0.027, loClip=0.1, deltaYmin=0.0005)
        현재 25쌍 중 23쌍 미달 → 목표 0쌍
AUTO-20 인접 표면 단계 간 대비 ≥ 1.25:1
AUTO-21 AUTO-17~20을 라이트·다크 양쪽에서 검사, 양쪽 통과

그리고 실제로 브라우저를 띄워 360×740 / 768×1024 / 1440×900 × 라이트·다크
= 6조합에서 13개 탭 전부를 확인한다. 각 항목에 확인 근거를 한 줄씩 기록한다.

M-1  6조합 전부 가로 스크롤 없음 (scrollWidth <= clientWidth)
M-2  텍스트 잘림·요소 겹침 없음
M-3  360px에서 좌우 여백 최소 16px
M-4  하단 고정 탭바가 어떤 콘텐츠도 가리지 않음
     (AI 입력창, 페이저, 마지막 카드, 모달 취소 버튼)
M-5  13개 탭이 동일한 시각 언어를 유지 (탭마다 달라 보이지 않음)
M-6  Tab만으로 모든 대화형 요소 도달 + 매 순간 포커스가 눈에 보임
M-7  Tab 순서가 시각적 순서와 일치
M-8  매도 모달: 포커스 트랩 / Escape 닫기 / 닫은 뒤 포커스 복원
M-9  키보드만으로 매도 슬라이더 확정 가능 + 단일 키로는 절대 체결 안 됨
M-10 OS 다크 설정 추종 / 수동 토글이 이김 / 새로고침 후 유지
M-11 테마 전환 시 FOUC 없음
M-12 "동작 줄이기" 켜면 애니메이션·부드러운 스크롤 정지
M-13 확대 200%에서 콘텐츠 손실·겹침 없음
M-14 한글이 어절 중간에서 끊기지 않음 (경고문·동의문·AI 답변)
M-15 30초 갱신 가격에서 숫자가 흔들리지 않음
M-16 흑백 스크린샷에서도 상승/하락 구분됨
M-17 상승=빨강 / 하락=파랑이 전 화면 유지
M-18 로딩→데이터 전환 시 레이아웃 점프 없음
M-19 빈 상태·오류·로딩이 6조합 전부 정상
M-20 설치형 PWA 상태바 색이 배경과 이어짐

회귀 방지:
R-1 매도 확인 단계 수 동일 (모달 → 슬라이드 90% → 확정)
R-2 MASTER 권한 게이팅 전부 유지
R-3 동의 체크박스 전부 존재, 기본값 꺼짐
R-4 면책·경고 문구 삭제 0건 (문자열 diff로 확인)
R-5 api() 호출 경로·메서드·바디 무변경 (grep diff)
R-6 적용된 분석/진행 중 분석의 삭제 차단 유지
R-7 폴링 주기 무변경 (추천 30초, AI 상세 3초, 가격 15초)
R-8 백엔드 파일 수정 0건 (git diff --stat)

## 루프

[0] 감사 스크립트 작성 → 기준선 측정 → baseline.json
[1] P0 → P1 → P2 순, 한 번에 번호 하나만
[2] 수정 (커밋 메시지에 항목 번호 명시)
[3] 자동 + 수동 + 회귀 검사 전체 실행
[4] 판정:
    - 전부 통과 → 다음 항목
    - 실패 → 원인 기록 후 [2]로
    - 같은 항목 3회 연속 실패 → 멈추고 무엇이 왜 막히는지 보고
[5] 종료 조건을 전부 만족했을 때만 완료 선언

종료 조건:
1. AUTO-1~21 전부 통과
2. M-1~20 전부 통과, 각 항목 확인 근거 기록됨
3. R-1~8 전부 통과
4. 라이트·다크 양쪽 × 13개 탭 스크린샷 확보, 시각 언어 일관
5. 변경 요약(무엇을 왜) + 남은 알려진 제약 정리

매 루프 보고 형식:
  ## 루프 N — 대상: (항목 번호)
  ### 변경     (파일:범위) 무엇을 왜
  ### 자동 검사  | ID | 기준 | 이전 | 현재 | 판정 | 표
  ### 수동 검사  각 항목 확인 근거 한 줄씩
  ### 회귀      R-1~8 결과
  ### 다음 루프에서 할 것

## 태도
- 기준을 만족시키기 위해 숫자를 조작하거나 검사를 우회하지 마라.
  (예: 감사 스크립트가 못 보는 곳에 색을 숨기기, 화이트리스트 남용)
- 기준끼리 충돌하면 임의로 한쪽을 버리지 말고 보고한다.
  (예: "상승=빨강 유지"와 "색맹 대응"이 충돌하는 지점)
- 확신이 없으면 추측해서 고치지 말고 무엇이 불명확한지 적는다.
- 기능이 바뀌었는지 애매하면 바꾸지 않는 쪽을 택한다. 이건 돈을 다루는 앱이다.
```

---

## 8. 참고 자료

- [Web Content Accessibility Guidelines (WCAG) 2.2 — W3C](https://www.w3.org/TR/WCAG22/) — SC 2.5.8 타깃 크기 24×24, SC 2.4.11 포커스 가림 방지
- [Deque University — WCAG 2.2 Updates](https://dequeuniversity.com/resources/wcag-2.2/)
- [APCA in a Nutshell](https://git.apcacontrast.com/documentation/APCA_in_a_Nutshell.html) / [The Easy Intro to APCA](https://git.apcacontrast.com/documentation/APCAeasyIntro.html) — 다크 모드에서 WCAG 2.x가 지각을 과대평가하는 이유
- [W3C Silver — Visual Contrast of Text Subgroup](https://www.w3.org/WAI/GL/task-forces/silver/wiki/Visual_Contrast_of_Text_Subgroup)
- [Dark Mode UI Design: 7 Best Practices for Accessible Dark Themes — atmos](https://atmos.style/blog/dark-mode-ui-best-practices) — 순검정 회피, 표면 밝기로 고도 표현, 강조색 채도 70~80%
- [Dark Mode UI in the Spotlight: 11 Tips for 2025 — Netguru](https://www.netguru.com/blog/tips-dark-mode-ui)
- [MDN — prefers-color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme)
- [Color Token Naming Conventions: Primitive, Semantic, Component](https://colorarchive.org/guides/color-token-naming-guide/) — 3티어 참조 방향 규칙
- [Design tokens explained — Contentful](https://www.contentful.com/blog/design-token-system/)
- [How to Build Accessible Modals with Focus Traps — UXPin](https://www.uxpin.com/studio/blog/how-to-build-accessible-modals-with-focus-traps/)
- [Dialogs — Stanford University Accessibility](https://uit.stanford.edu/accessibility/testing/quick-checks/dialogs)
- [Fintech UX Design: 10 Best Practices for Dashboards — Wildnet Edge](https://www.wildnetedge.com/blogs/fintech-ux-design-best-practices-for-financial-dashboards) — 점진적 공개, 역할별 1순위 지표
- [Fintech Dashboard Design: Patterns & Real Examples — Masterly](https://www.themasterly.com/blog/fintech-dashboard-design-guide)
- [Skeleton loading screen design — LogRocket](https://blog.logrocket.com/ux-design/skeleton-loading-screen-design/) — 400ms~3초 구간에서만 효과
- [어색하게 끊기는 한국어 줄바꿈 다듬는 법 — Dale Seo](https://daleseo.com/css-text-wrap/) — `word-break: keep-all`, `text-wrap: pretty`
- [웹 사이트들의 한글 타이포그래피 — lqez](https://lqez.github.io/blog/hangul-typo-on-web.html)
- [줄바꿈 스타일에 대한 A to Z: 다국어편 — Naver SmartStudio](https://smartstudio.tech/deepdive-linebreak-css-about-language/)
