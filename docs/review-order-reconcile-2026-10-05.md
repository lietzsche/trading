# 작업 12 — 미확인 자동 주문 재확인 완료

## 승인 범위와 구현

개발·테스트·검수는 모의 DB/API만 사용했다. 운영은 읽기 전용 상태 조회만 실행했으며 운영 재확인 API 호출/SQL 갱신/미확인 주문 생성은 하지 않았다. 배포 후 정상 코드가 Upbit 조회 결과에 따라 상태와 확인된 주문 이력을 갱신하는 범위로 사용자 승인을 받았다.

- 자동매매 계정 처리 시작에 모든 PENDING/UNKNOWN을 identifier로 GET `/v1/order` 재조회.
- 주문 uuid, identifier, market이 일치한 경우만 확인된 주문으로 처리. 해당 사용자 주문 이력이 없으면 저장하고 ACCEPTED로 갱신.
- 404 또는 400 `order_not_found`, 생성 후 2분 이상인 경우만 REJECTED.
- 네트워크/5xx/인증 오류/비정상·불일치 응답/2분 이내 미접수는 상태 그대로, 해당 주기 차단 유지.
- 재확인 헬퍼와 홈 API는 주문 POST를 하지 않는다. 정상 자동매매 주기는 미확인 주문이 모두 정리된 뒤 기존 조건으로 계속 판단한다.
- 홈 safety에 blocked 요약과 identifier·시장·생성 시각 추가. MASTER 전용 `POST /api/upbit/auto-orders/reconcile`는 본인 키로 재확인만 실행하며 결과 토스트/화면 갱신. USER/ADMIN은 403, 버튼 미노출.
- 자동매매/수동 매도와 같은 프로세스 잠금을 사용해 중복 재확인·주문 중 재확인 실행을 막는다.
- 사람이 상태를 직접 바꾸는 버튼·SQL·스크립트는 추가하지 않았다. 새 마이그레이션 없음.
- 사용 안내/README의 주문 안전 장치를 실제 자동 재확인·홈 경고·버튼 동작으로 수정. AI 매도 의견을 직접 주문하는 별도 기능은 이번 작업에 포함하지 않았다.

## 테스트 결과

| 검증 | 결과 |
| --- | --- |
| pytest (운영 네트워크 차단, 소스/테스트 읽기 전용 마운트) | 243 passed, 기존 Starlette warning 1 |
| Vitest | 8 files / 43 tests passed |
| production build | 성공, 295 modules, JS 495.13 kB / gzip 150.30 kB |
| ui-audit | AUTO-1~22 모두 통과 |
| git diff --check | 통과 |

회귀 테스트 (`test_auto_order_recovery.py`):

- `test_reconcile_confirmed_saves_history_once_and_accepts_without_post`: 이력 없음/있음 2케이스, 확인된 이력만 저장, GET-only.
- `test_reconcile_missing_old_only_rejects_and_never_posts`: 404/명시적 order_not_found 경과 후 정리, 2분 이내/500/401/403/다른 400/연결 오류는 유지, 8케이스 모두 GET-only.
- `test_reconcile_mismatched_response_keeps_blocked`: 잘못된 identifier 응답은 갱신 없음.
- `test_unresolved_order_blocks_next_cycle_after_failed_get_without_post`: 시작 재조회 실패 후 계정 차단, POST 없음.
- 기존 응답 유실 복구/조회 실패 테스트 유지.

API 테스트 (`test_main.py`):

- `test_reconcile_endpoint_master_only_and_lookup_only`: USER/ADMIN/MASTER 3케이스, 일반 자동매매 실행 호출 금지.
- `test_dashboard_unconfirmed_orders_override_healthy_state`: blocked 요약과 식별자/시장/생성 시각 응답 검증.

모의 브라우저 `scripts/check-usage-guide.cjs` (375×812):

- 홈 blocked 경고, MASTER 재확인 버튼, 1회 모의 재확인 요청, 결과 토스트와 화면 갱신 확인.
- USER 버튼 미노출, 다른 변경/주문 요청 금지, 가로 넘침 0.
- 사용 안내 6개, 등록된 키 사용자 첫 방문 안내와 재방문 숨김, pageerror 0.
- [홈 미확인 주문 화면](screenshots/work12-guide-2026-10-05/home-blocked-375.png)
- [사용 안내 화면](screenshots/work12-guide-2026-10-05/usage-guide-375.png)
- 검수 Vite 서버 정리.

## 커밋과 배포

- `0687a45` Upbit 조회 결과로 미확인 자동 주문 재확인
- `263267b` 홈 미확인 주문 경고와 재확인 버튼 및 안내 갱신
- 기존 사용 안내 커밋 `4243787`도 포함하여 `./reup.sh` 배포 완료. 푸시는 하지 않았다.
- API 이미지: `sha256:a9712724169bbef711a2126c2b303137cfe050b63ade9f66ae44a2cfbb50f87a`.
- 공개 health status/database/calculation 모두 UP, API ERROR/FATAL/Traceback 없음.
- 운영 읽기 전용 조회: 배포 전후 ACCEPTED 2건, PENDING/UNKNOWN 없음. 실제 미확인 주문을 만들거나 강제 재확인하지 않았으므로 분기 동작은 모의 테스트 근거이다.
- 정상 스케줄의 계산 `/v1/auto-trade/decide` HTTP 200 반복 확인(한국 시간 13:03:46, 13:04:16, 13:05:06).
- 고정 Cloudflare URL 유지. 모바일에서 더보기 → 사용 안내로 접근.
