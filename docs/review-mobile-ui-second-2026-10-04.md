# 작업 6 모바일 UI 검수

## 변경 내용

- 안내·AI 펼침·범례 글자색을 글자용 토큰으로 수정했다. 매도 경고 배경도 토큰으로 바꾸고, 슬라이더와 AI 상태 배지 대비를 개선했다.
- AUTO-22: CSS `color`에서 표면 토큰 사용을 차단한다. 단색 강조 버튼의 반전 글자는 `.primary`, `.install`, `.ai-page .primary`만 허용한다.
- 홈 보유 자산 및 추천 AI 바로가기는 `KRW-BTC`로 새 분석 입력을 연다. 기존 대화를 자동 선택하거나 분석을 자동 전송하지 않는다. 계좌 포함 동의는 꺼진 상태다.
- 긴 오류 값은 3줄로 접고 펼치기를 제공한다. 계산 설정은 변경 표시와 현재 → 변경 확인 시트를 거쳐 저장한다. 변화가 없으면 저장 버튼은 비활성이다. 하락 폭은 양수 입력·음수 저장이며 정수 및 기존 서버 검증 계약을 유지한다.
- 행동용 보조 버튼은 테두리와 최소 44px 높이를 갖는다. 추천은 원래 순위 번호, 1위 자동매수 우선 배지, 핵심 가격 정보 위주로 표시하며 기준가·갱신 정보는 상세로 접었다. 가격 갱신 설명은 정보 시트로 옮겼다.
- 성공 알림은 하단 메뉴 위 토스트로 4초 표시한다. 오류는 인라인으로 유지한다. 내 정보 저장 성공 알림을 추가했다.
- 기존 API만 사용하여 MASTER 사용자 권한 변경·비활성화와 메일 수신자 삭제를 확인 시트로 연결했다. 본인 MASTER 변경 버튼은 숨긴다.

## 테스트 결과

- pytest **178 passed**, 기존 Starlette 경고 1건. 운영 네트워크와 분리된 기존 테스트 이미지에서 실행했으며 이번 변경은 프런트/검수 스크립트뿐이다.
- Vitest **28 passed / 4 files**, 프로덕션 빌드 성공.
- `scripts/ui-audit.mjs`: **AUTO-1~22 모두 통과**. CSS 하드코딩 색 0, 반경 5종, 글자 크기 8종, `!important` 0, 라이트·다크 토큰 대비 검사 통과.
- Playwright 모의 API 전체 검수 통과. 운영 주문·설정·사용자·메일 변경 요청과 유료 AI 호출은 하지 않았다.
- `account_ai_shortcut_opens_prefilled_new_analysis`, `recommendation_ai_shortcut_opens_prefilled_new_analysis`: 양 테마에서 새 분석 폼과 `KRW-BTC` 입력 확인, 자동 분석 요청 0건.
- `settings_save_requires_confirmation_and_negative_drawdown`: 확인 전 및 취소 시 PUT 0건, 확인 후 1건, 양수 입력 12를 음수 -12로 전송. 저장 성공 후 버튼 비활성 및 4초 토스트 종료 확인.
- 사용자 권한 변경과 메일 삭제도 확인 전 요청 0건, 확인 후 요청 및 목록 갱신 확인. 본인 권한 변경 컨트롤 미노출 확인.
- 이전 실패는 visualViewport를 제거한 모의 환경의 포인터 조작 시간 초과였다. 해당 미지원 환경은 키보드 Enter로 보기 전환하여 확인했다. 일반 환경의 모바일 보기 전환은 포인터로 통과했다.

## 실측

375×812, 라이트·다크 모두: 헤더 44px, 주식·Upbit 기본 카드 **173.97px**, 첫 화면 완전히 보이는 카드 **3개**. 펼친 상세와 긴 운영 종목명은 높이가 달라질 수 있다. 모든 캡처 화면 가로 넘침 0, 44px 미만 터치 대상 0, 브라우저 런타임 오류 0.

렌더링 대비 검사는 글자 페인트를 잠시 숨긴 스크린샷의 실제 배경 픽셀(그라디언트 포함)과 계산된 글자색·불투명도로 WCAG 비율을 산출한다. 현재 뷰포트에 보이고 가려지지 않은 텍스트 노드를 검사하며 비활성 컨트롤은 제외한다. 홈, 매도 확인, 자동매매 켜기 확인, 성공 토스트, AI 근거, 새 분석 입력의 양 테마 **실패 0**. 최저 비율은 라이트 AI 근거 **4.51:1**. 전체 스크롤 콘텐츠·입력값·플레이스홀더의 모든 픽셀 검사를 의미하지는 않는다.

AI 대화 회귀: 375×812 스레드 451.20px, 입력 영역 102px, 하단 732.20px < 메뉴 상단 733.20px. 360×740 스레드 379.20px. 첫 방문·재방문 동일. visualViewport 키보드 모의 스레드 190px, 실제 안드로이드 키보드는 미검수다.

R-1 매도 확인·슬라이더 게이트, R-2 MASTER 권한, R-3 동의 기본 꺼짐, R-4 위험 안내, R-5 API 계약, R-6 진행/적용 기록 삭제 보호, R-7 기존 폴링 주기를 유지했다. R-8 백엔드 변경 없음. 모의 브라우저와 기존 백엔드 테스트로 확인했다. 운영 데이터 전체·실제 휴대폰 검수를 대신하지 않는다.

원시 수치: [metrics.json](screenshots/mobile-ui-second-2026-10-03/metrics.json).

## 375×812 스크린샷

| 화면 | 라이트 | 다크 |
| --- | --- | --- |
| 홈 | [보기](screenshots/mobile-ui-second-2026-10-03/light-home.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-home.png) |
| 매도 확인 | [보기](screenshots/mobile-ui-second-2026-10-03/light-sell-confirm.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-sell-confirm.png) |
| 성공 토스트 | [보기](screenshots/mobile-ui-second-2026-10-03/light-success-toast.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-success-toast.png) |
| Upbit 추천 | [보기](screenshots/mobile-ui-second-2026-10-03/light-upbit.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-upbit.png) |
| 계산 설정 확인 | [보기](screenshots/mobile-ui-second-2026-10-03/light-settings-confirm.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-settings-confirm.png) |
| 사용자 | [보기](screenshots/mobile-ui-second-2026-10-03/light-users.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-users.png) |
| 오류 | [보기](screenshots/mobile-ui-second-2026-10-03/light-errors.png) | [보기](screenshots/mobile-ui-second-2026-10-03/dark-errors.png) |
