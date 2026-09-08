# Trading

개인 서버에서 주식·Upbit 추천과 Upbit 자동매매를 운영하는 프로젝트입니다.

## 구성

- `trade-service`: Spring Boot 사용자/관리자 UI, 인증, 스케줄, 주문 실행, PostgreSQL 저장
- `calculation-service`: FastAPI + Pandas 기반 추천·가격 갱신·자동매매 의사결정
- `postgres`: 영속 데이터 저장

계산 서비스는 Docker 내부 네트워크에서만 접근할 수 있습니다. Upbit API 키와 실제 주문 실행은 `trade-service`에 남아 있으며 주문 금액과 최소 주문 금액 검증도 Java에서 수행합니다.

기존 `admin-server`, `registry-server`, `edge-server` 기능은 제거했습니다. 시스템 상태와 오류는 `trade-service`의 관리자 페이지에서 확인합니다.

## 배포

루트 `.env` 파일에 `POSTGRES_PASSWORD`를 설정한 뒤 실행합니다.

```bash
./up.sh
```

서비스와 Cloudflare Quick Tunnel 하나를 시작하고 URL을 `.quick-tunnels/urls.env`에 저장합니다. 기존 URL을 유지하면서 재배포하려면 다음을 실행합니다.

```bash
./reup.sh
```

관리자 페이지:

- `/admin/system`: trade-service, calculation-service, JVM 및 오류 상태
- `/admin/errors`: 주식·Upbit 작업 오류 조회
- `/admin/setting`: 계산 설정
- `/admin/autos`: 자동매매 설정

`ADMIN` 또는 `MASTER`만 관리자 페이지와 상세 Actuator 엔드포인트에 접근할 수 있습니다. `/actuator/health`와 `/actuator/info`만 배포 상태 확인을 위해 공개됩니다.

## 테스트

```bash
docker build --target test -t trading/calculation-service:test calculation-service
docker run --rm trading/calculation-service:test

docker run --rm \
  -v "$PWD/trade-service:/workspace" \
  -v 001_maven_test_cache:/root/.m2 \
  -w /workspace \
  maven:3.9.9-eclipse-temurin-21 \
  mvn test
```

## 전체 정리

```bash
./down.sh
```

`down.sh`는 컨테이너, 네트워크, Quick Tunnel과 PostgreSQL 데이터 볼륨 `001_postgres_data`를 삭제합니다. 데이터는 복구할 수 없습니다.
