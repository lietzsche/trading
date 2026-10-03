# 작업 5 — 모바일 AI 대화 후속 수정 검수

## 반영 내용

1. AI 설정/연결 관리 이동 요청은 App의 안정된 소비 콜백으로 처리 직후 0으로 초기화한다. 컴포넌트를 다시 마운트해도 이전 시트 열기·스크롤이 재실행되지 않는다.
2. 모바일 chat 보기는 투자 판단 카드·별도 목록 버튼·분석 헤더를 숨기고 보기 탭 아래 44px 도구 모음으로 통합했다. 목록, 투자 위험 안내, 설정(자동 적용 경고 점), 대화 메뉴를 제공한다. 삭제/숨김·새 분석·되돌리기는 대화 메뉴에서 접근한다. 기존 위험 안내 내용은 삭제하지 않고 시트로 제공한다.
3. 메시지 입력은 한 줄로 시작해 최대 네 줄(96px)까지 늘어난다. 보내기는 44px 아이콘 버튼, 계좌 포함은 기본 꺼짐 스위치 칩, 전송 항목은 별도 안내 시트다. 빈 입력의 계좌 동의 포함 작성 영역은 102px이다.
4. 고정 `470px` 예약 공간을 제거했다. 실제 공통 헤더 아래 위치와 하단 메뉴 높이(safe-area 포함)를 측정해 `--mobile-chat-height`로 제공하며 flex로 스레드에 남은 높이를 배정한다. 문서가 아닌 스레드만 스크롤한다. 모바일 summary의 상태 칩도 세 열 한 줄로 제공한다.
5. visualViewport 축소 시 전체 뷰포트 높이를 CSS 변수로 반영하고 키보드가 열린 동안 공통 헤더/하단 메뉴를 숨겨 입력과 최소 120px 스레드를 확보한다. visualViewport가 없으면 innerHeight와 resize 이벤트를 사용한다. 레이아웃 측정 후 새 답변으로 스크롤해 초기 레이아웃 변경으로 인한 맨 아래 이동 누락도 방지한다.
6. 선택 사항인 경량 `GET /api/upbit/key/status`를 구현했다. 로그인한 본인 키의 비어 있지 않은 필드 존재 여부만 DB에서 조회하며 응답은 `{"registered": bool}`뿐이다. 키 원문·마스킹 문자열을 반환하지 않고 Upbit 계좌를 호출하지 않는다. 실제 Upbit 인증 성공 여부를 뜻하는 값은 아니다. 연결 관리 화면은 기존 dashboard 대신 이 API를 이용한다.

백엔드 업무 변경은 6)의 키 상태 조회(피드백 4번)와 해당 회귀 테스트뿐이다. 계산·주문·자동 판단·DB 마이그레이션은 변경하지 않았다.

## 이동 요청 재현 테스트

`scripts/mobile-ux-check.cjs`의 Playwright 모의 API 검수에서 라이트·다크 각각 확인했다.

- `ai_settings_request_consumed_on_remount`: 더보기 → AI 설정에서 시트 1개 확인 → Esc → 홈 → AI 재진입 시 시트 0개. **통과**.
- `connections_request_consumed_on_remount`: 더보기 → 연결 관리에서 scrollIntoView 1회 → 홈 → 내 정보 일반 재진입 후 누적 횟수 여전히 1회. **통과**.
- `new_reply_polling_scrolls_to_bottom`: 후속 메시지를 RUNNING으로 모의 응답하고 기존 3초 폴링에서 완료 답변을 반환했다. 긴 답변이 도착한 뒤 스레드 scrollTop이 맨 아래로 이동함을 확인했다. **통과**.

## 모바일 치수

완료된 기존 분석이 있는 키 등록 사용자, 첫 방문은 localStorage 비움, 재방문은 안내 접힘 저장 상태로 검수했다. 라이트·다크의 수치가 동일하다. 새 분석 입력 폼이나 긴 글 작성으로 입력이 확장된 상태의 수치는 아니다.

| 크기 | 방문 | 스레드 높이 | 입력 상단 y | 입력 하단 y | 하단 메뉴 상단 y | 문서 높이/뷰포트 |
|---|---|---:|---:|---:|---:|---|
| 375×812 | 첫 방문 | 451.20px | 630.20px | 732.20px | 733.20px | 812 / 812 |
| 375×812 | 재방문 | 451.20px | 630.20px | 732.20px | 733.20px | 812 / 812 |
| 360×740 | 첫 방문 | 379.20px | 558.20px | 660.20px | 661.20px | 740 / 740 |
| 360×740 | 재방문 | 379.20px | 558.20px | 660.20px | 661.20px | 740 / 740 |

모든 조합에서 작성 영역 102px, document scrollWidth = clientWidth, scrollHeight = clientHeight, 44px 미만 터치 대상 0개. 작은 체크박스는 연결된 실제 클릭 label을 기준으로 검사한다. 전송 아이콘의 접근성 이름은 `보내기`다. 최대 입력 높이 96px과 계좌 동의 기본 꺼짐도 검사했다. 운영 데이터 전체의 모든 링크·메시지 형태까지 확인한 수치는 아니며 모의 데이터 화면 기준이다.

원시 자료: [metrics.json](screenshots/mobile-chat-followup-2026-10-03/metrics.json).

## 키보드 검수 범위

**실제 안드로이드 기기에서 키보드를 연 검수와 스크린샷: 미검수.** 접근 가능한 안드로이드 기기/ADB 연결이 없어 실기기 사진을 제공할 수 없다.

Chromium에서 visualViewport 높이를 400px로 모의 축소하고 textarea를 포커스한 테스트는 통과했다. 헤더·하단 메뉴가 숨겨지고 스레드 190px, 입력 하단 399px로 확인했다. visualViewport를 제공하지 않는 모의 환경에서도 375px 화면의 스레드 400px 이상을 유지했다. 이 결과는 실제 모바일 키보드/노치/브라우저 주소창 동작까지 검증했다는 뜻이 아니다. 실기기 Chrome과 설치된 PWA에서 한 차례 확인이 필요하다.

## 자동 검사와 회귀

- 현재 소스 기반 테스트 이미지: pytest **169 passed**, 기존 Starlette deprecation warning 1건. 운영 네트워크와 분리한 `docker run --rm --network none trading/api-service:test`로 실행.
- 신규 pytest: `test_upbit_key_status_returns_only_registration[False]`, `test_upbit_key_status_returns_only_registration[True]`, `test_upbit_key_status_requires_authentication`. 등록 상태 두 경우, 응답 필드 제한·본인 조회·외부 계좌 호출 없음, 비인증 401을 확인했다.
- Vitest **25 passed / 3 files**, Vite 프로덕션 빌드 성공.
- `node scripts/ui-audit.mjs`: **AUTO-1~21 전부 통과**. 하드코딩 CSS 색 0, 원시 색 참조 37, 반경 5종, 폰트 크기 8종, !important 0. 양 테마 대비 검사 통과.
- 브라우저 런타임 오류 0, 1440×900에서는 기존 grid 대화 레이아웃과 인라인 설정 유지.
- R-3 동의 기본 꺼짐, R-4 위험·전송 안내 시트 문구, R-6 진행 항목 체크 차단·적용 기록 숨김/되돌리기 메뉴, R-7 기존 3초 폴링 및 새 답변 자동 스크롤을 검수했다. 기존 자동매매 켜기 확인 전 PUT 0건·확정 후 1건·끄기 즉시 실행 테스트도 유지했다.

재실행: 프런트 폴더에서 `./node_modules/.bin/vite --host 127.0.0.1 --port 5179`를 띄우고 루트에서 `PLAYWRIGHT_MODULE=/tmp/trading-ui-check/node_modules/playwright node scripts/mobile-ux-check.cjs` 실행. 다른 환경에서는 Playwright 설치 경로와 Chromium 설치를 먼저 준비한다. 모든 API를 모의 응답하므로 실제 거래 요청은 발생하지 않는다.

## 375×812 스크린샷

| 화면 | 라이트 | 다크 |
|---|---|---|
| AI 요약 | [보기](screenshots/mobile-chat-followup-2026-10-03/light-ai-summary.png) | [보기](screenshots/mobile-chat-followup-2026-10-03/dark-ai-summary.png) |
| AI 대화 첫 방문 | [보기](screenshots/mobile-chat-followup-2026-10-03/light-chat-first-375.png) | [보기](screenshots/mobile-chat-followup-2026-10-03/dark-chat-first-375.png) |
| AI 대화 재방문 | [보기](screenshots/mobile-chat-followup-2026-10-03/light-chat-returning-375.png) | [보기](screenshots/mobile-chat-followup-2026-10-03/dark-chat-returning-375.png) |

## 운영 반영

이번 요청은 검토·수정·커밋까지로 처리했다. 재배포와 push는 실행하지 않았다. 운영 설정·분석 기록은 수정하지 않았다. 배포하려면 `./reup.sh`로 프런트와 새 키 상태 API를 함께 반영하면 된다.
