# Upbit MA40 Auto Trader

Upbit KRW 마켓에서 **40일 단순 이동평균(MA40)** 한 가지 기준으로만 실제 자동매매하는 개인용 서비스입니다. 주식, 배당, AI 분석 기능은 이 브랜치의 API와 화면에서 제거했습니다.

## 전략

- 오늘 진행 중인 일봉은 평균에서 제외합니다.
- 직전 완료 일봉 40개의 종가 평균을 MA40으로 계산합니다.
- 현재가가 MA40 이상이면 매수 후보, MA40 아래이면 매도 신호입니다.
- 신호는 5분마다, 주문 판단은 30초마다 실행합니다.
- 코인을 보유하지 않을 때 첫 주문 가능 후보에 사용 가능한 KRW로 시장가 매수하며 분할 매수하지 않습니다.
- 미확인 주문, 인증 오류, 최소 주문금액, 거래 제한 잔고에 대한 기존 안전장치는 유지합니다.

수익을 보장하지 않으며 횡보장에서는 잦은 매매, 수수료, 슬리피지로 손실이 날 수 있습니다.

## 로컬 실행

Docker와 Docker Compose v2, OpenSSL이 필요합니다.

```bash
chmod +x local-up.sh
./local-up.sh
```

`.env`가 없으면 `local-up.sh`가 강한 임의 PostgreSQL 비밀번호를 생성합니다. 직접 관리하려면 `.env.example`을 복사해 먼저 설정해도 됩니다.

브라우저에서 `http://localhost:8001`을 엽니다. 최초 실행에서는 회원가입이 열리며 첫 계정 하나가 생성되면 추가 가입은 자동으로 잠깁니다. 운영 시에는 `SIGNUP_ENABLED=false`로 실행하는 것을 권장합니다.

종료(데이터 유지):

```bash
docker compose down
```

`down.sh`는 DB 볼륨까지 삭제하므로 초기화 의도가 있을 때만 사용하세요.

## Upbit 설정

1. Upbit Open API 관리에서 키를 만듭니다.
2. 앱의 `설정`에 표시되는 **서버 공인 출구 IP**를 Upbit 키의 허용 IP로 등록합니다.
3. 자산 조회와 주문 권한만 부여하고 **출금 권한은 부여하지 않습니다**.
4. 앱의 `설정`에서 Access Key와 Secret Key를 저장합니다.
5. `모니터링`에서 계좌와 MA40 신호가 정상인지 확인합니다.
6. 처음에는 소액으로 `자동매매 켜기`를 사용합니다.

Upbit는 실제 API 호출지의 공인 IP와 허용 IP가 같아야 합니다. 가정용 유동 IP, VPN, 프록시, 재생성되는 클라우드 IP는 바뀔 수 있으므로 운영 서버에는 고정 공인 IP를 권장합니다. 화면의 IP는 서버가 외부 HTTPS 서비스에 직접 요청해 확인한 값이며 5분간 캐시됩니다.

키는 `SESSION_SECRET`으로 사용자별 암호화됩니다. `.runtime.env`를 잃거나 비밀값을 바꾸면 키를 다시 등록해야 합니다.

## 화면

- **모니터링**: 자동매매 상태, 평가액, MA40 신호, 자산, 최근 주문
- **설정**: 고정 전략 설명, Upbit 키 등록, 자동매매 on/off
- **백테스트**: 종목·기준 봉 수·기간·초기 자금·수수료·슬리피지 설정과 전략/단순 보유 수익률·거래 내역. 백테스트 기준 봉을 바꿔도 실제 자동매매는 MA40으로 유지됩니다.
- **가이드**: 전략 계산, 주문 흐름, 장애 시 동작, 운영 주의사항

## 테스트

```bash
docker build --target test -t trading/calculation-service:test calculation-service
docker run --rm trading/calculation-service:test

cd api-service/frontend
npm ci
npm test
npm run build
```

## 운영 배포

기존 Cloudflare Named Tunnel을 사용하는 운영 환경은 `.env`와 `.cloudflare-tunnel-token`을 설정한 뒤 `./up.sh`를 사용합니다. 공개 배포 전 `SIGNUP_ENABLED=false`, 강한 `POSTGRES_PASSWORD`, 안전하게 보관한 `.runtime.env`를 확인하세요.
