### 서비스 (USER)페이지
- [GO USER PAGE](http://lietzsche.iptime.org:8080)

---

### 주식 및 Upbit(coin) 시세분석 및 Upbit 자동매매 소프트웨어
- spring-eureka: 통합 도구(MSA)
- spring-admin: 로그 확인 및 운영 도구
- openFeign: 통합 내부 및 외부 통신 도구
- spring-security 6

#### 특징
- 계산로직: 주식, upbit 메서드 팩토리 패턴으로 같은 로직을 통해 계산
- spring-admin(admin-server): 모니터링 프로젝트 로그인 시 core 프로젝트(trade-service)의 유저 중 ADMIN or MASTER 권한의 유저로만 인증하도록 설정

### docker 사용시 빌드 명령어(root폴더에서 실행)
- docker-compose up -d

### 개인 서버 배포 (Cloudflare Quick Tunnel)

`cloudflared`가 설치된 서버의 루트 폴더에서 실행합니다.

```bash
./up.sh
```

Docker 서비스를 빌드·실행한 뒤 `trade-service`와 `admin-server`용 임시 공개 URL을 각각 출력합니다. URL은 `.quick-tunnels/urls.env`에도 저장됩니다. Quick Tunnel URL은 터널을 새로 시작할 때마다 바뀝니다.

코드 변경 후 기존 URL을 유지하면서 재배포하려면:

```bash
./reup.sh
```

컨테이너, 네트워크, Quick Tunnel과 모든 관련 볼륨을 완전히 삭제하려면:

```bash
./down.sh
```

> **주의:** `down.sh`는 외부 PostgreSQL 볼륨 `001_postgres_data`까지 삭제합니다. 저장된 DB 데이터는 복구할 수 없습니다.
