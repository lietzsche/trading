# Trading

개인 서버에서 주식·Upbit 추천과 Upbit 자동매매를 운영하는 프로젝트입니다.

## 구성

- `calculation-service`: FastAPI + Pandas 기반 추천·가격 갱신·자동매매 의사결정
- `api-service`: FastAPI 인증·수집·스케줄·주문 API와 React 사용자/관리자 화면
- `postgres`: 영속 데이터 저장

계산 서비스와 PostgreSQL은 Docker 내부 네트워크에서만 접근할 수 있습니다. Upbit API 키, 주문 가능 금액, 최소 주문 금액 검증과 실제 주문 실행은 `api-service`가 담당합니다.

기존 Java 서비스는 모두 제거했습니다. 시스템 상태와 오류는 React 관리자 화면에서 확인합니다.

## 국내·미국 주식과 배당

주식/배당 화면의 **전체·국내·미국** 필터로 시장을 선택합니다. 국내 가격은 KRW, 미국은 USD로 표시하며 원화 환산은 하지 않습니다. 미국 주식·ETF는 무료 공개 데이터의 호출 부하를 제한하기 위해 기본 관심 목록 40개부터 수집합니다. 미국 전체 상장 종목을 모두 검색하는 기능은 아닙니다.

루트 `.env`의 `US_STOCK_SYMBOLS`에 티커를 쉼표로 지정할 수 있습니다(최대 100개). 예: `US_STOCK_SYMBOLS=AAPL,MSFT,KO,O,SCHD`. 저장 코드와 AI 직접 입력은 `US:AAPL` 형식이며 AI 입력창에서는 `AAPL`도 자동 변환합니다. 추천은 기존 계산 조건을 통과한 종목만 표시하므로 등록한 티커가 모두 추천에 나타나는 것은 아닙니다. 주식 계산 설정은 국내/미국이 공유합니다. 미국 주식 주문 실행이나 미국 증권 계좌 연동은 추가하지 않았습니다.

미국은 Yahoo Finance 공개 일봉·배당 이벤트를 사용합니다. 실시간 호가/공식 SLA가 보장되는 데이터가 아닙니다. 5분 캐시와 요청 간격을 두며 429 발생 시 10분간 새 요청을 쉬도록 했습니다. 미국 동부 시간대(서머타임 반영)로 수집·5분 가격 갱신·이력 저장·배당 수집을 예약합니다. 가격 갱신은 평일 09~16시, 추천 수집은 평일 08:30, 배당은 매일 18:00, 이력은 평일 17:30입니다. 거래소 휴장일 달력 연동은 없으며 휴장일에는 최신 제공 일봉이 유지됩니다.

미국 배당수익률은 최근 365일 기록된 주당 배당 이벤트 합계 / 최근 일봉 종가 × 100입니다. 국내 제공자 수익률과 집계 방법이 다르며 세금·환율·미래 지급을 반영하지 않습니다. 지급일은 추정해 채우지 않으며 최근 배당락일만 제공합니다. 집계 기간에 주식 분할이 있으면 정확하지 않은 배당수익률을 표시하지 않도록 제외합니다. AI 미국 백테스트도 USD·완료 일봉 기준이며 환율과 모든 기업행동을 완전히 재현하지 않습니다.

## 오류 기록 보존

DB 오류 기록은 기본 **마지막 발생 후 30일·최근 10,000개 묶음** 중 더 짧은 범위만 보존합니다. 동일 source·operation·error_type이 마지막 발생 후 10분 이내에 반복되면 새 행 대신 횟수와 마지막 발생 시각을 갱신하며 최초 메시지는 유지합니다. 다른 종목의 같은 유형 오류도 한 묶음에 포함될 수 있습니다. 스케줄러 시작 시와 매시간 `trade_error_log`만 정리합니다. 거래/주문/AI 분석 이력은 삭제하지 않습니다. `.env`에서 `ERROR_LOG_RETENTION_DAYS`(1~3650), `ERROR_LOG_MAX_RECORDS`(100~1,000,000)를 설정할 수 있고 실제 적용 값은 오류 화면에 표시합니다. 정리된 오류는 백업이 없으면 복구할 수 없습니다. 기존 데이터는 마지막 발생 시각이 없으면 최초 기록 시각을 사용합니다.

API·계산 서비스·Postgres의 Docker 로그는 컨테이너별 10MB × 3개로 순환합니다. 새 설정과 V009·V010 마이그레이션은 `./reup.sh` 때 적용됩니다. 보존 정책이 처음 실행되면 기존 오래된 오류도 정리되므로 필요한 기록은 **재배포 전에 별도로 보관**하세요.

## 배포

루트 `.env` 파일에 `POSTGRES_PASSWORD`를 설정한 뒤 실행합니다.

```bash
./up.sh
```

React/FastAPI는 Cloudflare Named Tunnel을 통해 고정 주소 `https://trade.lietzsche.org`로 공개합니다. 최초 1회 Cloudflare 대시보드의 **Networking(네트워킹) > Tunnels(터널)**에서 터널을 생성하고, 게시된 애플리케이션 경로를 `trade.lietzsche.org`에서 `http://localhost:8001`로 연결하세요. 대시보드가 보여주는 실행 명령의 토큰 값만 저장소 루트의 `.cloudflare-tunnel-token`에 저장한 뒤 권한을 제한합니다.

```bash
chmod 600 .cloudflare-tunnel-token
./up.sh
```

토큰 파일과 런타임 상태는 Git에서 제외됩니다. 기존 URL을 유지하면서 재배포하려면 다음을 실행합니다.

```bash
./reup.sh
```

배포 URL은 `API_SERVICE_URL`로 표시됩니다. `ADMIN` 또는 `MASTER`만 관리자 API를 사용할 수 있고, 사용자 비밀번호와 세션 쿠키는 BCrypt 및 서명된 HttpOnly/Secure 쿠키로 보호됩니다.

DB 마이그레이션이 성공한 뒤 API와 주문 스케줄러가 시작되며, 재배포는 서비스 정상 상태까지 확인합니다. DB 또는 계산 서비스 장애 시 `/api/health`는 HTTP 503을 반환합니다.

Android Chrome에서 배포 URL을 연 뒤 메뉴의 **앱 설치** 또는 화면의 **앱으로 설치**를 누르면 홈 화면 앱처럼 사용할 수 있습니다. PWA 셸과 정적 자산만 오프라인 캐시하며 거래 API와 계좌 데이터는 항상 네트워크에서 새로 조회합니다.

## AI 전략 분석

관리자 화면의 **AI 분석** 탭에서 개인 DeepSeek API 키를 등록해 주식·Upbit 전략 후보를 분석할 수 있습니다. 키는 사용자별로 암호화해 저장하며 화면과 로그에는 원문을 다시 표시하지 않습니다. 계좌 요약 전송은 기본적으로 꺼져 있고 실행할 때마다 사용자가 선택합니다.

분석 결과는 현재 설정과 동일한 과거 시세·거래 비용으로 백테스트해 비교합니다. 데이터가 부족한 후보는 적용할 수 없으며, 검증된 설정도 `MASTER`가 최신 설정을 다시 확인하고 명시적으로 승인해야 반영됩니다. AI는 설정 후보만 제안하고 주문을 직접 실행하거나 자동매매 상태를 변경하지 않습니다. 앱 자체의 일일 대화 제한은 두지 않고 DeepSeek 계정의 잔액·속도·사용 한도를 따르며, 개별 요청에는 실행 시간과 출력 길이 안전 제한을 적용합니다.

주식과 Upbit 모두 추천 종목을 화면에서 최대 5개까지 선택할 수 있습니다. 완료된 분석에서는 후속 질문을 이어갈 수 있고, AI는 필요할 때 완료 일봉이나 고정된 Google News RSS의 제목·출처·게시 시각을 조회합니다. 기사 본문을 읽은 것으로 간주하지 않으며 링크에서 원문을 직접 확인해야 합니다. 후속 질문도 사용량에 포함되고, 대화 중 제안된 설정은 바로 적용할 수 없습니다.

AI 화면은 대화 목록과 메시지 창으로 구성됩니다. 새 대화의 첫 질문은 설정 후보 백테스트를 포함하는 정식 분석이며, 이후 메시지는 같은 분석 맥락을 이어받아 추가 조사와 설명을 제공합니다. 과거 분석 기록도 각각 하나의 대화방으로 그대로 표시됩니다.

진행 중이거나 실제 설정을 적용한 감사 기록을 제외한 AI 대화는 화면에서 삭제할 수 있습니다. 자동매수는 추천 화면과 동일하게 갱신 단계 내림차순, 같은 단계에서는 목표 도달 우선순위 순으로 첫 종목을 선택합니다.

## 테스트

```bash
docker build --target test -t trading/calculation-service:test calculation-service
docker run --rm trading/calculation-service:test

docker build --target test -t trading/api-service:test api-service
docker run --rm trading/api-service:test

cd api-service/frontend
npm ci
npm test
npm run build

```

GitHub push/PR에서도 같은 Python·프런트엔드 테스트를 실행합니다. CI에서는 자동매매가 비활성화되며 운영 DB·API 키를 사용하지 않습니다.

## 점검 결과와 다음 개발

[운영 코드 점검 기록](docs/review-2026-09-12.md)에 이번 개선 사항과 남은 개발 우선순위를 정리했습니다.
특히 주문 응답 불명확 시 복구, DB 백업·초기 DDL, 전체 주문 이력 페이징이 다음 우선 과제입니다.

## 전체 정리

```bash
./down.sh
```

`down.sh`는 컨테이너, 네트워크, 로컬 Cloudflare Tunnel 연결과 PostgreSQL 데이터 볼륨 `001_postgres_data`를 삭제합니다. 데이터는 복구할 수 없습니다. Cloudflare에 등록된 Named Tunnel과 `trade.lietzsche.org` DNS 설정은 다음 배포에서도 같은 URL을 쓰도록 보존됩니다.
### DB 백업과 복원 검증

`./scripts/backup.sh`는 PostgreSQL custom 형식 백업을 `backups/YYYYmmdd-HHMM.dump`에 생성합니다(한국 시간, 권한 600, 최근 14개 유지). 백업에는 민감한 데이터가 포함되므로 별도 안전한 저장소에도 보관하세요.

`./scripts/restore.sh backups/파일.dump`는 기본적으로 별도 임시 DB에만 복원하고 주요 테이블 행 수를 출력한 뒤 임시 DB를 삭제합니다. 운영 DB는 변경하지 않습니다. 운영 덮어쓰기는 `--force`와 터미널에서 `RESTORE` 확인 입력이 모두 필요합니다. 운영 복원 전 자동매매/API 중지와 최신 백업이 필수입니다.

매일 03:00 한국 시간 백업 예시(crontab은 직접 등록):

```cron
CRON_TZ=Asia/Seoul
0 3 * * * /home/stxtory/001/scripts/backup.sh >> /home/stxtory/001/backups/cron.log 2>&1
```

첫 백업으로 `backups/`를 먼저 생성하고, cron의 Docker 실행 권한과 시간대 지원을 확인하세요. 백업과 별도로 `.runtime.env`의 `SESSION_SECRET`도 안전하게 보관해야 합니다.
### API 키 암호화 주의

Upbit와 DeepSeek 키는 `SESSION_SECRET`에서 사용자별로 파생한 키로 암호화됩니다. **SESSION_SECRET을 바꾸거나 잃으면 기존 키를 복호화할 수 없으므로 DeepSeek·Upbit 키를 다시 등록해야 합니다.** `.runtime.env`를 백업과 별도로 안전하게 보관하세요. 앱 기동 시 기존 Upbit 평문 키는 한 트랜잭션으로 암호화 전환되며 키 값은 로그에 출력하지 않습니다.
