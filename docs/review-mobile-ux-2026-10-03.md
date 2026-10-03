# 모바일 UX 개선 검수 — 작업 4

## 반영 내용

작업 3 커밋 `22179ed`를 먼저 `./reup.sh`로 배포한 뒤 진행했다. 이번 변경은 프런트엔드와 검수 자료만 포함한다.

- 홈 자동매매는 꺼짐 → 켜짐에 확인 시트와 기존 90% 슬라이더를 필수로 거친다. 전액 시장가 매수 가능성을 안내한다. 끄기는 즉시 실행한다.
- 설정 비교표의 현재값은 보조 본문 토큰을 사용하며 모바일에서는 현재/AI 추천 라벨을 표시한다.
- AI 설정 버튼과 키·정기 판단·자동 적용 상태 칩을 제공한다. 칩은 해당 설정 섹션을 펼쳐 이동한다. 모바일 설정 시트는 닫기/Esc/Tab 순환/포커스 복귀를 지원한다.
- Upbit 키 관리를 내 정보 → 연결 관리로 이동했다. DeepSeek 등록 상태와 AI 설정 바로가기도 제공한다.
- 하단 메뉴에 SVG 아이콘과 라벨을 함께 표시한다. 더보기는 행형 메뉴이며 AI 설정·연결 관리·테마와 로그아웃을 제공한다.
- 모바일의 중복 브랜드 헤더와 완료 배지를 제거하고 제목·새로고침만 표시한다. 로그아웃과 테마는 더보기에서 이용한다.
- AI 안내는 첫 방문에 펼치고 이후 접힌 상태를 저장한다. 대화 목록은 한 줄 버튼에서 시트로 열며 선택·필터·페이징·삭제 기능을 유지한다. 긴 답변은 대화 영역 내부에서 스크롤한다.
- 계좌 요약 동의는 기본 꺼짐이며 전송 항목 설명은 펼침으로 제공한다. 입력창 반경을 일반 입력 토큰으로 변경했다. 근거·설정의 검증 조건·주의 사항·사용 자료는 접고 후보 목록은 펼친다.
- 키 미등록 사용자에게만 3단계 최초 안내 카드를 제공하며 닫은 상태를 저장한다. localStorage 접근은 try/catch로 보호한다.

## 테스트와 수치

- 현재 소스로 만든 테스트 Docker 이미지에서 `docker run --rm --network none trading/api-service:test`: **166 passed**, 기존 Starlette deprecation warning 1건.
- Vitest: **25 passed / 3 files**. 프로덕션 Vite 빌드 성공.
- `node scripts/ui-audit.mjs`: **AUTO-1~21 모두 통과**. 하드코딩 CSS 색 0, 원시 색 참조 37, 반경 5종, 폰트 크기 8종, `!important` 0. 라이트·다크 대비 검사 모두 통과.
- `scripts/mobile-ux-check.cjs`: Chromium **375×812**, 모의 API로 양 테마 검수. 운영 주문·설정 API는 호출하지 않았다. 16개 화면의 브라우저 런타임 오류 0.
- 확인 시트 진입/Enter 단독/취소에서는 `/upbit/auto` PUT **0건**. 슬라이더 90% + Enter 후 `{auto_on:true}` 1건. 끄기는 확인 없이 `{auto_on:false}` 1건.
- 선택 모드의 행 탭 체크, 진행 중 메시지 선택 차단, 입력창 숨김, Esc 닫기와 포커스 복귀, 동의 기본 꺼짐, 안내 접힘 저장을 확인했다. 1440×900에서 설정은 인라인이고 대화 작업 영역은 grid로 유지됨을 확인했다. USER 역할의 AI·계산 설정 메뉴 미노출을 확인했다.

| 측정 항목 | 라이트 | 다크 |
|---|---:|---:|
| 공통 헤더 높이 | 44px | 44px |
| AI 대화 입력 영역 상단 y | 526.39px | 526.39px |
| document scrollWidth / clientWidth | 375 / 375 | 375 / 375 |
| 44px 미만 터치 대상 | 0 | 0 |

입력 영역 y는 등록된 키·완료된 분석·접힌 안내의 재방문 상태를 기준으로 측정했다. 첫 방문 안내 또는 전송 설명을 펼치면 세로 스크롤을 허용한다. 입력·송신 영역이 하단 메뉴에 가리지 않고 답변 영역은 내부 스크롤임을 테스트했다. 터치 대상 검사는 열린 시트 또는 해당 페이지에서 CSS상 표시된 모든 버튼·summary·폼 컨트롤·링크를 대상으로 하며 체크박스는 실제 클릭 가능한 연결 label의 크기로 판정한다. 운영 데이터 전체 및 실제 안드로이드 키보드까지 검수한 결과는 아니다.

원시 측정 자료: [metrics.json](screenshots/mobile-ux-2026-10-03/metrics.json).

## 375×812 스크린샷

| 화면 | 라이트 | 다크 |
|---|---|---|
| 홈 | [보기](screenshots/mobile-ux-2026-10-03/light-home.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-home.png) |
| 자동매매 켜기 확인 | [보기](screenshots/mobile-ux-2026-10-03/light-auto-confirm.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-auto-confirm.png) |
| Upbit | [보기](screenshots/mobile-ux-2026-10-03/light-upbit.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-upbit.png) |
| AI 판단 요약 | [보기](screenshots/mobile-ux-2026-10-03/light-ai-summary.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-ai-summary.png) |
| AI 대화 | [보기](screenshots/mobile-ux-2026-10-03/light-ai-chat.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-ai-chat.png) |
| AI 설정 시트 | [보기](screenshots/mobile-ux-2026-10-03/light-ai-settings.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-ai-settings.png) |
| 더보기 | [보기](screenshots/mobile-ux-2026-10-03/light-more.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-more.png) |
| 내 정보 연결 관리 | [보기](screenshots/mobile-ux-2026-10-03/light-connections.png) | [보기](screenshots/mobile-ux-2026-10-03/dark-connections.png) |

## R 회귀 항목

| 항목 | 결과 및 확인 방법 |
|---|---|
| R-1 매도 모달 → 슬라이드 90% → 확정 | 통과: 매도 함수·조건·포인터 및 키보드 임계값 무변경. 재사용 컴포넌트에 동작별 라벨만 추가. 슬라이더 확인 게이트는 모의 브라우저 테스트로 검증. |
| R-2 MASTER 권한 게이팅 | 통과: 기존 매도·적용·자동 판단 조건 유지, 새 상태 칩/바로가기도 기존 역할에 맞춤. USER 메뉴 제한 브라우저 검수 및 백엔드 권한 테스트 통과. |
| R-3 동의 기본 꺼짐 | 통과: 기존 동의 state 및 요청값 유지, 후속 계좌 동의 unchecked 브라우저 검사. |
| R-4 면책·경고 | 통과: 투자 위험·전송 개인정보 안내를 삭제하지 않고 접이식으로 이동. 전액 시장가 매수 경고 추가. |
| R-5 API 계약 | 통과: 기존 변경 API 경로/메서드/바디 유지. 키 변경 폼의 화면 위치만 이동. 연결 상태는 기존 GET dashboard/config로 조회. |
| R-6 기록 삭제 보호 | 통과: 적용 기록 숨김, 진행 분석/메시지 삭제 차단 유지. 진행 행 체크 불가 브라우저 검사 및 pytest 통과. |
| R-7 폴링 주기 | 통과: 추천 30초, AI 상세 3초, 가격 신선도 15초 타이머 무변경. 모바일 자동 스크롤 대상만 내부 대화 영역으로 변경. |
| R-8 백엔드 무변경 | 통과: 작업 3 이후 이번 변경에 app/tests/계산 서비스/DB/Compose 변경 없음. |

## 운영 반영 범위

사용자의 이번 배포 요청에 따라 작업 3의 V008 마이그레이션을 포함해 재배포했다. 작업 3 당시 보고서의 미배포 상태는 당시 기록이며 이번 요청으로 운영 반영되었다. 운영 설정·분석 데이터에 수동 쓰기 또는 삭제 테스트는 하지 않았다. 정상 운영 스케줄러는 배포 이후 기존처럼 실행된다. 이번 모바일 작업도 `./reup.sh`로 반영했고 Cloudflare 고정 URL과 터널을 유지했다.

재배포 종료 코드 0. API·계산 서비스·Postgres 모두 healthy, 마이그레이션 정상 종료. `/api/health`의 status/database/calculation 모두 UP, `https://trade.lietzsche.org` HTTP 200을 확인했다. 배포 직후 로그에서 오류·예외는 발견하지 않았다. 이미 존재하는 컬럼/인덱스의 skipping NOTICE는 재실행 가능한 DDL의 정상 메시지다. 8001은 여전히 127.0.0.1에만 바인딩된다.
