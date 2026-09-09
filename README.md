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

## 테스트

```bash
docker build --target test -t trading/calculation-service:test calculation-service
docker run --rm trading/calculation-service:test

docker build --target test -t trading/api-service:test api-service
docker run --rm trading/api-service:test

```

## 전체 정리

```bash
./down.sh
```

`down.sh`는 컨테이너, 네트워크, Quick Tunnel과 PostgreSQL 데이터 볼륨 `001_postgres_data`를 삭제합니다. 데이터는 복구할 수 없습니다.
