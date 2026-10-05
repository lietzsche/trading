# 작업 13 — 종료 보호 및 매도 불가 잔고

## 구현

- 종료 플래그 설정 → 스케줄러 신규 실행 중단 → 주문 잠금 최대 20초 대기 → Upbit 클라이언트 종료. 시간 초과는 경고 로그만 남기며 기존 미확인 주문 재확인 흐름을 유지한다.
- 종료 시 신규 자동 주기·수동 매도·관리자 재확인 진입을 차단한다. lifespan 정리는 finally에서 수행한다.
- Docker 종료 유예는 40초로 설정해 기본 10초 SIGKILL이 20초 대기를 끊지 않도록 한다.
- 검증된 KRW 마켓 목록과 유효한 시세를 받은 경우에만 미지원/최소 주문 금액 미만 잔고를 계산 입력에서 제외한다. 최소 금액은 orders/chance의 ask.min_total, 누락 시 5,000원이다.
- 수량은 balance + locked. 목록·시세 조회 실패, 잔고/시세 형식 오류, 최소 금액 조회 실패는 기존 보유 판단을 유지한다. 정상 자산은 기존 매도·보유 판단을 그대로 유지한다.
- 제외 자산은 매도 실행에서도 보호한다. 계정·통화별 당일 INFO 안내를 메모리에서 중복 방지하며 오류 DB에는 기록하지 않는다. 프로세스 재시작 시 안내 캐시는 초기화된다.
- 홈 계좌에는 자산과 평가금을 유지하고 “매도 불가 소액·미지원” 표시 및 해당 매도 버튼 숨김을 적용했다.

## 검수

운영 DB에 연결하지 않는 Docker `--network none` 테스트와 모의 DB만 사용했다. 테스트 주문은 모의 처리이며 실제 주문 POST는 실행하지 않았다.

| 검사 | 결과 |
|---|---|
| pytest | 260개 통과, 기존 Starlette deprecation 경고 1개 |
| Vitest | 8개 파일 / 43개 테스트 통과 |
| Vite build | 성공 |
| ui-audit | AUTO-1~22 전부 통과 |

추가 테스트:

- `test_stop_waits_for_order_before_client_close`: 주기 잠금 해제 전에 close 없음, 해제 후 close, 신규 주기 차단.
- `test_stop_timeout_closes_client_and_warns`: 제한 시간 초과 시 경고 후 close.
- `test_unsellable_classification_preserves_locked_holdings`: 미지원·소액 제외, 정상/잠긴 정상 잔고 유지(4개).
- `test_unsellable_lookup_failure_preserves_holdings`: 목록·시세·최소 금액 조회 실패 시 제외 없음(3개).
- `test_unsellable_balances_buy_or_preserve_sell`: 계산 API 계약을 모의해 미지원/소액만 보유하면 BUY, 정상 보유는 SELL/HOLD, 목록 실패는 기존 SELL 판단 유지. 두 주기를 돌려 INFO 중복 없음 및 오류 DB 기록 없음도 확인(5개).
- `test_snapshot_unsellable_badge_preserves_asset_valuation`: 홈 표시용 사유와 계좌 평가금 유지(3개).

운영 DB 조회는 배포 전 AI 작업 상태 집계 SELECT만 수행했다(분석 12개·후속 메시지 1개 모두 COMPLETED). 수동 SQL 데이터 변경·새 마이그레이션·실제 주문 테스트 없음. 배포 후 기존 스케줄러의 정상 운영 처리는 유지된다.

## 배포

- 기능 커밋: `0a79dde` — 종료 중 주문 보호와 매도 불가 잔고 판단 보완.
- `./reup.sh` 성공. Named Tunnel 및 고정 URL 유지. calculation-service 빌드 단계는 전부 캐시였고 기존 컨테이너를 유지했다.
- API 이미지: `sha256:5d7e450b0ac0a6b93ec948099c2a0d4a28042b13144506a589c79484e10ccd4c`.
- API 컨테이너 healthy, 실제 StopTimeout=40 확인.
- 외부 `https://trade.lietzsche.org/api/health`: HTTP 200, status/database/calculation 모두 UP.
- 시작 로그 정상, 검수 시점 신규 오류 로그 없음. 실제 운영 주문을 검증 목적으로 실행하거나 운영 잔고를 변경하지 않았다.
