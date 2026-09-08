package com.uj.stxtory.service.order;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.uj.stxtory.domain.dto.upbit.UPbitAccount;
import java.math.BigInteger;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

// TODO 추후에 openFeign으로 변경
// 일단 restTemplate을 빈으로 등록 예정
public class UPbitOrderServiceSample {
  public static void main(String[] args) {
    String accessKey = ""; // DB에서 가져오기
    String secretKey = "";

    UPbitOrderServiceSample order = new UPbitOrderServiceSample();
    //		order.getNow(accessKey, secretKey);
    try {
      order.execute(
          "KRW-ETH",
          "0.38168799",
          "bid",
          accessKey,
          secretKey); // 매수 TODO 최소주문금액 이상으로 주문해주세요 에러까지 확인: 진짜 테스트 해봐야 함
      //			order.execute("KRW-XRP", "242.91667581", "ask", accessKey, secretKey);// 매도 TODO 테스트 해야
      // 함; 현재 매도하기엔 이익을 보는 중이라 될 때 예정
    } catch (NoSuchAlgorithmException e) {
      // TODO Auto-generated catch block
      e.printStackTrace();
    }
  }

  /**
   * 전체 계좌 조회 GUIDE:
   * docs.upbit.com/reference/%EC%A0%84%EC%B2%B4-%EA%B3%84%EC%A2%8C-%EC%A1%B0%ED%9A%8C
   */
  public void getNow(String accessKey, String secretKey) {
    String serverUrl = "https://api.upbit.com/v1/accounts";

    // JWT 생성
    Algorithm algorithm = Algorithm.HMAC256(secretKey);
    String jwtToken =
        JWT.create()
            .withClaim("access_key", accessKey)
            .withClaim("nonce", UUID.randomUUID().toString())
            .sign(algorithm);

    String authenticationToken = "Bearer " + jwtToken;

    // RestTemplate 사용
    RestTemplate restTemplate = new RestTemplate();

    // 요청 헤더 설정
    HttpHeaders headers = new HttpHeaders();
    headers.set("Content-Type", "application/json");
    headers.set("Authorization", authenticationToken);

    // 요청 생성
    HttpEntity<String> entity = new HttpEntity<>(headers);

    ResponseEntity<List<UPbitAccount>> response =
        restTemplate.exchange(
            serverUrl,
            HttpMethod.GET,
            entity,
            new ParameterizedTypeReference<List<UPbitAccount>>() {});

    List<UPbitAccount> accounts = response.getBody();
    System.out.println(accounts);
    // 응답 출력
    accounts.forEach(
        account -> {
          System.out.println("Currency: " + account.getCurrency());
          System.out.println("Balance: " + account.getBalance());
          System.out.println("Locked: " + account.getLocked());
          // 기타 필요한 정보 출력
        });
  }

  /**
   * 매수 주문하기 GUIDE: https://docs.upbit.com/reference/%EC%A3%BC%EB%AC%B8%ED%95%98%EA%B8%B0
   *
   * <p>시장가 매도 매수 예정
   */
  public void execute(
      String market, String priceOrVolume, String side, String accessKey, String secretKey)
      throws NoSuchAlgorithmException {
    String serverUrl = "https://api.upbit.com";

    // 요청 파라미터 설정
    Map<String, String> params = new HashMap<>();
    params.put("market", market);
    params.put("side", side); // 매수 bid, 매도 ask

    if ("bid".equals(side)) params.put("price", priceOrVolume); // 지정가, 시장가 매수 시에만 필수
    if ("ask".equals(side)) params.put("volume", priceOrVolume); // 지정가, 시장가 매도 시에만 필수

    if ("bid".equals(side))
      params.put("ord_type", "price"); // price : 시장가 주문(매수), market : 시장가 주문(매도)
    if ("ask".equals(side)) params.put("ord_type", "market"); // market : 시장가 주문(매도)

    // 쿼리 해시 생성
    String queryString =
        params.entrySet().stream()
            .map(entry -> entry.getKey() + "=" + entry.getValue())
            .reduce((p1, p2) -> p1 + "&" + p2)
            .orElse("");

    MessageDigest md = MessageDigest.getInstance("SHA-512");
    md.update(queryString.getBytes());
    String queryHash = String.format("%0128x", new BigInteger(1, md.digest()));

    // JWT 토큰 생성
    Algorithm algorithm = Algorithm.HMAC256(secretKey);
    String jwtToken =
        JWT.create()
            .withClaim("access_key", accessKey)
            .withClaim("nonce", UUID.randomUUID().toString())
            .withClaim("query_hash", queryHash)
            .withClaim("query_hash_alg", "SHA512")
            .sign(algorithm);

    String authenticationToken = "Bearer " + jwtToken;

    // RestTemplate 설정 및 요청 전송
    RestTemplate restTemplate = new RestTemplate();
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("Authorization", authenticationToken);

    HttpEntity<Map<String, String>> requestEntity = new HttpEntity<>(params, headers);

    try {
      ResponseEntity<String> response =
          restTemplate.exchange(
              serverUrl + "/v1/orders", HttpMethod.POST, requestEntity, String.class);
      System.out.println("Response: " + response.getBody());
    } catch (Exception e) {
      e.printStackTrace();
    }
  }

  // TODO -> 미체결 주문 자동 취소로직 상기

}
