# 작업 8 — 추천 선정식 반올림 제거 검수

## 변경 범위

- `_is_recommended`의 최근 종가와 하락 기준가 비교에서 `round()`만 제거했다. 다른 계산식은 변경하지 않았다.
- 검증 스크립트에 `--live-rule unrounded`를 추가해 배포된 계산 API와 새 선정식을 대조할 수 있게 했다.
- 운영 DB는 읽기 전용 트랜잭션으로 조회했다. 설정·추천 기록을 직접 변경하거나 주문을 실행하지 않았다.

## 회귀 테스트

계산 서비스 test 이미지를 빌드하고 네트워크 없이 실행: **96 passed, 1 warning**(기존 Starlette 경고).

- `test_selection_compares_fractional_threshold_without_integer_rounding`: BONK(0.00444 < 0.0046024) 제외, BLAST(0.553 > 0.5192) 선정, 국내 고가 종목 고정 데이터 결과 불변.
- `test_domestic_high_price_record_keeps_selection_result`: 운영 이력에서 고정한 이오테크닉스(039030) 3개 봉으로 결과 불변 확인. 종가 536,000원, 하락 기준가 533,900원이며 다른 선정 조건에서 제외된다.
- `git diff --check` 통과.

## 읽기 전용 이력 재분석

배포 전 기본 옵션, 배포 후 `--live-rule unrounded`로 실행했다. 두 실행의 비교 결과가 같고, 배포 후 계산 API와 새 선정식의 결과도 일치했다. 배포 후 스냅샷: 2026-10-04 12:20:21 UTC.

| 시장 | 종목 수 | 최신 선정(반올림 → 제거) | 과거 비교 건수 | 과거 추가 | 과거 제외 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 국내 | 1,819 | 163 → 163 | 12,627 | 0 | 0 |
| Upbit | 293 | 12 → 12 | 16,573 | 28 | 14 |
| 미국 | 0 | 미검증 | 0 | 미검증 | 미검증 |

기존 보고서와 국내 차이 0, Upbit 추가 28·제외 14가 일치한다. 이는 저장된 이력의 종목·시점별 선정 비교이며 현재 추천이 28개 늘어난다는 뜻이나 수익률 백테스트 결과가 아니다. 미국은 저장된 가격 이력이 없어 영향 평가 불가.

## 단독 배포

코드 커밋: `b287e7a`(추천 선정식의 정수 반올림 제거).

```sh
docker compose up -d --build --no-deps --wait --wait-timeout 180 calculation-service
docker compose exec -T api-service python - --live-rule unrounded < scripts/analyze-selection-rounding.py
```

- calculation-service만 production 이미지 재빌드 및 컨테이너 교체. 새 이미지: `sha256:56525b0f08ec2fa70dd24f4d31a4b1f6640d7831b0a3432ebc7801869b30af5e`.
- api-service 컨테이너 ID `da6a73bfe8e2…`, DB 컨테이너 ID `2d0f3afe30d2…`와 이미지가 배포 전후 동일하다. 터널과 DB 마이그레이션은 건드리지 않았다.
- 계산 컨테이너 Healthy. 공개 `/api/health`: status/database/calculation 모두 UP.
- 다음 정상 계산 주기부터 새 선정식이 사용된다. 추천 재수집·자동 주문을 검수 목적으로 강제 실행하지 않았다.
- 푸시는 하지 않았다.
