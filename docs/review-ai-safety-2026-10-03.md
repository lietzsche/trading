# AI 자동 설정 적용 안전성 검수

## 판정과 변경

최대 낙폭은 양수이며 클수록 나쁘므로 후보 낙폭 ≤ 기존 낙폭 + 2%p로 수정했다. 자동 적용에는 검증 20일 이상, 청산 3건 이상, 기존보다 높은 수익률도 요구한다. 누락·비유한 수치와 음수 낙폭은 거부한다. 백엔드 `auto_apply_eligible`과 프런트 `autoApplyEligible`을 사용해 자동 적용, 추천 표시와 수동 확인 경고를 통일했다.

시장별 마지막 자동 적용 이후 기본 72시간 대기한다. `AUTO_APPLY_COOLDOWN_HOURS`로 지정하며 다음 가능 시각은 한국 시간으로 기록한다. 설정 행 잠금 이후 마지막 적용을 조회해 동시 자동 적용을 보호한다. 추천 변경 지문에는 종목 코드, 갱신 단계, 목표가·손절가와 설정만 포함한다. 추천 변경 모드에도 최소 실행 간격을 적용한다.

MASTER의 본인 소유 적용 기록만 되돌릴 수 있다. 분석과 설정 행을 같은 트랜잭션에서 잠그고 현재 설정이 적용 후보와 일치할 때만 스냅샷으로 복원한다. 이후 변경, 중복 복원과 타인 소유는 거부한다. V008은 복원 시각·수행자 컬럼과 자동 적용 조회 인덱스를 추가한다. `docker-compose.yml`의 마이그레이션 목록에 등록했다.

수동 적용 화면에 검증 수익률·최대 낙폭·청산 횟수 비교와 자동 기준 미달 경고를 추가했다. 자동 판단 필터는 ref를 사용해 설정 초안 초기화와 상세 폴링 재시작을 피한다. 선택 모드에서 행을 누르면 체크를 토글하고 모바일 메시지 입력창은 숨긴다. 요약 화면의 대화 선택은 대화 보기로 전환한다.

## 검수 결과

- API pytest: **166 passed**, Starlette 기존 deprecation warning 1건.
- Vitest: **25 passed**, 3개 파일. Vite 프로덕션 빌드 성공.
- Compose 구성과 `git diff --check` 통과.
- Chromium 375×812 모의 API: 복원 값 확인 모달·복원 완료 표시, 행 탭 선택, 선택 중 입력창 숨김, 진행 항목 보호, 혼합 삭제·숨김·건너뛰기, 빈 페이지 복귀 확인.
- 운영과 분리된 `trading-ai-safety-db` PostgreSQL 15 컨테이너(네트워크 없음, tmpfs 데이터)에 테스트 행을 만들고 V008을 두 번 실행했다. 기존 테스트 행 1개 보존, 복원값 NULL 유지, 두 번째 실행 성공을 확인했다. 테스트 컨테이너는 검수 후 삭제했다.

### 1~3번 신규 테스트

- `test_auto_apply_drawdown_and_return_gate`: 5.93 기준으로 8.42 거부, 7.90·2.00 허용, 수익률 동일·하락 거부.
- `test_auto_apply_rejects_missing_nonfinite_and_negative_metrics`
- `test_auto_apply_cooldown_blocks_recent_and_allows_elapsed`: 1시간 경과 거부, 73시간 경과 허용.
- `test_automation_fingerprint_ignores_live_price_changes`
- `test_recommendation_change_respects_minimum_interval`: 간격 내 미실행, 간격 경과 실행.
- Vitest `automatic settings safety`: `drawdown %s and return %s eligibility is %s` 5개 케이스, `rejects missing nonfinite and negative metrics`.

### 되돌리기 검증 방법

`SafetyDatabase`/`SafetyCursor` 모의 DB에 적용 후보와 스냅샷을 제공해 `test_revert_restores_snapshot_only_when_current_matches_applied`로 정상 복원과 후속 변경 409를 확인했다. 기록된 SQL에서 설정 `FOR UPDATE`, 정확한 복원 값과 `reverted_at` 기록을 검사했다. `test_revert_rejects_repeated_and_foreign_analysis`로 중복·조회 불가 기록을 검사했다. 브라우저 복원 검수도 모의 응답으로 진행했다.

## 운영 변경 범위

운영 `deal_settings` 및 `ai_analyses`에 쓰기 작업을 수행하지 않았다. 운영 마이그레이션과 재배포는 수행하지 않았다. 재배포 시 스케줄러가 기록을 변경할 수 있어 읽기 전용 조건을 보존했다. 코드·테스트·마이그레이션은 준비됐으며, 이후 운영 반영은 `./reup.sh`로 가능하다.
