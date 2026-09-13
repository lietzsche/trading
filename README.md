# Trading

개인 서버에서 주식·Upbit 추천과 Upbit 자동매매를 운영하는 프로젝트입니다.

## 구성

- `calculation-service`: FastAPI + Pandas 기반 추천·가격 갱신·자동매매 의사결정
- `api-service`: FastAPI 인증·수집·스케줄·주문 API와 React 사용자/관리자 화면
- `postgres`: 영속 데이터 저장

계산 서비스와 PostgreSQL은 Docker 내부 네트워크에서만 접근할 수 있습니다. Upbit API 키, 주문 가능 금액, 최소 주문 금액 검증과 실제 주문 실행은 `api-service`가 담당합니다.

기존 Java 서비스는 모두 제거했습니다. 시스템 상태와 오류는 React 관리자 화면에서 확인합니다.

## 배포

루트 `.env` 파일에 `POSTGRES_PASSWORD`를 설정한 뒤 실행합니다.

```bash
./up.sh
```

React/FastAPI용 Cloudflare Quick Tunnel 하나를 시작하고 URL을 `.quick-tunnels/urls.env`에 저장합니다. 기존 URL을 유지하면서 재배포하려면 다음을 실행합니다.

```bash
./reup.sh
```

배포 URL은 `API_SERVICE_URL`로 표시됩니다. `ADMIN` 또는 `MASTER`만 관리자 API를 사용할 수 있고, 사용자 비밀번호와 세션 쿠키는 BCrypt 및 서명된 HttpOnly/Secure 쿠키로 보호됩니다.

DB 마이그레이션이 성공한 뒤 API와 주문 스케줄러가 시작되며, 재배포는 서비스 정상 상태까지 확인합니다. DB 또는 계산 서비스 장애 시 `/api/health`는 HTTP 503을 반환합니다.

Android Chrome에서 배포 URL을 연 뒤 메뉴의 **앱 설치** 또는 화면의 **앱으로 설치**를 누르면 홈 화면 앱처럼 사용할 수 있습니다. PWA 셸과 정적 자산만 오프라인 캐시하며 거래 API와 계좌 데이터는 항상 네트워크에서 새로 조회합니다.

## AI 전략 분석

관리자 화면의 **AI 분석** 탭에서 개인 DeepSeek API 키를 등록해 주식·Upbit 전략 후보를 분석할 수 있습니다. 키는 사용자별로 암호화해 저장하며 화면과 로그에는 원문을 다시 표시하지 않습니다. 계좌 요약 전송은 기본적으로 꺼져 있고 실행할 때마다 사용자가 선택합니다.

분석 결과는 현재 설정과 동일한 과거 시세·거래 비용으로 백테스트해 비교합니다. 데이터가 부족한 후보는 적용할 수 없으며, 검증된 설정도 `MASTER`가 최신 설정을 다시 확인하고 명시적으로 승인해야 반영됩니다. AI는 설정 후보만 제안하고 주문을 직접 실행하거나 자동매매 상태를 변경하지 않습니다. 분석 요청은 DeepSeek 사용료가 발생할 수 있으므로 사용자별 일일 횟수·토큰 한도를 설정합니다.

주식과 Upbit 모두 추천 종목을 화면에서 최대 5개까지 선택할 수 있습니다. 완료된 분석에서는 후속 질문을 이어갈 수 있고, AI는 필요할 때 완료 일봉이나 고정된 Google News RSS의 제목·출처·게시 시각을 조회합니다. 기사 본문을 읽은 것으로 간주하지 않으며 링크에서 원문을 직접 확인해야 합니다. 후속 질문도 사용량에 포함되고, 대화 중 제안된 설정은 바로 적용할 수 없습니다.

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

`down.sh`는 컨테이너, 네트워크, Quick Tunnel과 PostgreSQL 데이터 볼륨 `001_postgres_data`를 삭제합니다. 데이터는 복구할 수 없습니다.
