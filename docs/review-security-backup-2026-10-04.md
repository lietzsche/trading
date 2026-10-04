# 작업 11 검수 보고 — 인증·키 보호·백업

검수/배포일: 2026-10-04 (Asia/Seoul). 푸시는 하지 않음.

## 구현과 커밋

| 항목 | 구현 | 주요 커밋 |
| --- | --- | --- |
| 1 인증 | 기본 가입 차단/공개 설정 API, 아이디·IP 이중 DB 잠금, 세션 버전, 현재 비밀번호 검증 | 54ffc55, f975dc7, f7881c0 |
| 2 키 보호 | 공통 key_cipher, 사용자별 Upbit 암호화, 평문 호환/기동 전환, 암호문 원본으로 키 교체 확인 | ace6d62, f16ff9e, f8bdaa9 |
| 3 백업 | custom dump/600/14개 보존, 기본 임시 복원, 운영 복원은 --force + 대화형 확인 | f1c6e32 |
| 4 주문 | identifier 선기록, POST 유실 시 GET 복구, 확인 불가 시 계정 차단 | 462086b |
| 5 프런트 | 성공 응답만 캐시, 의존성 5개 lock 버전 고정, 숨긴 탭 폴링 중지/복귀 즉시 조회 | 4229312, bd58e3f |

V011 인증, V012 주문 요청, V013 암호문 저장 컬럼 용량 마이그레이션을 배포 목록에 추가했다. 기존 키 컬럼 255자로는 입력 상한 길이의 Fernet 암호문을 수용할 수 없어 TEXT로 확장했다(기존 값 보존).

## 최종 검증 수치

- 최종 `trading/api-service:test` 이미지 빌드 후 네트워크 없이 실행: **pytest 226 passed, 1 warning**. 기존 Starlette deprecation 경고.
- **Vitest 7 files / 42 tests passed**.
- production frontend build 성공: 294 modules, JS 488.18 kB / gzip 148.04 kB.
- **ui-audit AUTO-1~AUTO-22: 22/22 통과**.
- `git diff --check`, 백업/복원 `bash -n` 통과.
- 실제 주문 POST/비밀번호 변경/로그아웃/가입 테스트는 운영이 아닌 모의 환경에서만 실행했다. DeepSeek 유료 호출 없음.

## 항목별 테스트 이름과 결과

인증 (`test_auth_security.py`, 11 케이스 모두 통과):

- `test_signup_disabled_and_enabled`: valid 가입 요청 차단 403 / 허용 201.
- `test_fifth_failure_locks_sixth_and_valid_password_until_expiry`: 실패 5회 후 다음 요청 429, 올바른 비밀번호도 잠금, 만료 후 성공, 아이디 카운트 초기화.
- `test_ip_scope_blocks_different_login_ids`: 아이디를 바꾸어도 IP 잠금.
- `test_logout_invalidates_previous_cookie`: 로그아웃 전 쿠키 재사용 401.
- `test_password_change_requires_correct_current_password`: 누락/불일치 모두 400.
- `test_password_change_invalidates_session`: 비밀번호 변경 후 이전 세션 401.
- `test_cloudflare_address_is_trusted_only_from_connector`: 로컬 프록시 CF 주소 우선, 비신뢰 연결의 헤더 무시, 잘못된 IP 헤더는 연결 주소로 대체.

추가로 운영과 네트워크가 분리된 임시 PostgreSQL에서 `scripts/check-auth-security-db.py` 실행: 동시 실패 5개가 두 scope에 각각 정확히 5회 저장, 6번째/정상 비밀번호 잠금 429, 새 Database 인스턴스에도 유지, 만료 후 성공 및 아이디 카운트 삭제 확인. V011~V013 각각 2회 적용 성공, 세션 버전 기본값 0 확인. 임시 컨테이너는 정리했다.

키 보호 (`test_credentials.py`, 7 케이스 모두 통과):

- `test_upbit_encrypted_and_plaintext_compatibility`: DB 암호문은 원문과 다름, 암호문/평문 호환, 타 사용자 복호화 거부.
- `test_private_key_boundary_decrypts_without_mutating_comparison_values`: API 호출은 평문 키, DB 비교용 원본은 암호문 그대로.
- `test_startup_plaintext_conversion_is_atomic_and_idempotent`: 트랜잭션 전환 및 2회 실행 시 두 번째 전환 0건.
- `test_key_save_encrypts_and_account_route_decrypts`: 저장/계좌 실제 API 경계 검증.
- `test_ai_account_summary_uses_decrypted_key`: AI 계좌 요약 호출 검증.
- `test_auto_order_decrypts_but_key_replacement_checks_ciphertext`: 자동 주문 시 평문 호출/암호문 비교, 교체 시 POST 없음.

주문 (`test_auto_order_recovery.py`, 3 케이스 모두 통과):

- `test_auto_order_response_loss_recovers_or_stops_without_reposting`: POST 이전 DB 기록, 응답 유실 시 같은 identifier로 GET 복구, 조회도 실패하면 UNKNOWN 기록/중단. 두 경우 모두 POST는 1회뿐.
- `test_unresolved_order_blocks_next_cycle_without_exchange_calls`: 미확인 주문이 남으면 다음 주기에도 신규 주문 차단.

프런트 (7개 신규 케이스 모두 통과):

- `visiblePolling.test.js`: hidden 중 조회 0, 다시 visible이면 즉시 1회 및 3초 주기 재개, 초기 hidden/요청 중 cleanup 검증.
- `sw.test.js`: navigate/일반 GET 각각 response.ok true/false의 4가지 캐시 동작 검증.
- `scripts/check-security-ui.cjs`: 375×812 모의 브라우저에서 가입 false 버튼 0개 / true 1개. GET-only 모의 요청.

## 백업과 복원 결과

`backups/20261004-2300.dump` 생성(한국 시간). custom 형식, 파일 권한 **600**, 크기 1,373,443 bytes, gitignore 확인. 기본 restore 모드로 고유 임시 DB에 복원했고 아래 운영 읽기 전용 행 수와 모두 일치했다. 임시 DB는 종료 시 삭제되며 운영 DB를 덮어쓰지 않았다.

| 테이블 | 운영 조회 | 임시 복원 |
| --- | ---: | ---: |
| tb_user | 1 | 1 |
| tb_upbit_key | 1 | 1 |
| upbit | 472 | 472 |
| upbit_order_history | 30 | 30 |
| ai_analyses | 10 | 10 |

이 백업은 암호화 전환 전 시점이므로 평문 Upbit 키를 포함할 수 있다. Git에는 포함되지 않으며 파일을 안전하게 보관해야 한다. crontab 등록은 하지 않았다. README에 일일 실행 예시와 SESSION_SECRET 별도 보관 주의를 추가했다.

## 배포 후 운영 확인

- `./reup.sh` 완료. 고정 터널 URL 유지. 새 API 이미지 `sha256:42d850dba6dfafb214342f794455adeeb449db79e94b905df66eb3d2b7de1e98`.
- 공개 health: status/database/calculation 모두 UP.
- 공개 auth/config: signup_enabled=false. 운영 375×812 브라우저에서도 가입 버튼 0개(로그인/변경 요청 없음).
- tb_upbit_key 전체 1건 / access·secret 둘 다 암호문 prefix인 행 1건. 키 값 자체는 출력하지 않았다.
- 활성 자동매매 계정 1건. 정상 스케줄에서 `/v1/auto-trade/decide` HTTP 200 반복 확인: 한국 시간 23:25:09, 23:25:39, 23:26:09 등. 검수 목적으로 주문이나 스케줄 실행을 강제하지 않았다.
- 최근 3분 오류 기록 0건. API ERROR/Traceback/FATAL 없음.
- 배포 전 진행 중 AI 분석/후속 메시지 0건, 기존 추천 중복 그룹 0건 확인. 운영 비밀번호/자동매매 설정/분석 기록을 테스트 목적으로 수정하지 않았다. 기존 Upbit 평문 키만 요청된 기동 전환으로 암호화했다. 기존 정상 운영 스케줄은 유지했다.

## 사용 시 주의

- 세션 형식이 바뀌므로 기존 로그인은 다시 해야 한다. 비밀번호 변경과 로그아웃은 다른 기기의 기존 쿠키도 무효화한다.
- SESSION_SECRET 변경/분실 시 DeepSeek·Upbit 키를 다시 등록해야 한다.
- 접수 여부가 미확인인 자동 주문은 안전을 위해 다음 주기도 차단한다. 실제 Upbit 주문과 identifier를 확인한 뒤 관리자가 상태를 정리해야 한다. 무조건 재주문하지 않는다.
- 복원 `--force`는 구현했지만 운영 덮어쓰기 모드는 실행하지 않았다.
