package com.uj.stxtory.service.account.upbit;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.uj.stxtory.domain.dto.key.UPbitKey;
import com.uj.stxtory.domain.dto.upbit.UPbitAccount;
import com.uj.stxtory.domain.dto.upbit.UPbitOrderResponse;
import com.uj.stxtory.domain.dto.upbit.UpbitOrderChanceResponse;
import com.uj.stxtory.domain.entity.TbUPbitKey;
import com.uj.stxtory.repository.TbUPbitKeyRepository;
import com.uj.stxtory.service.account.PublicIpClient;
import feign.FeignException;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@Transactional(readOnly = true)
public class UPbitAccountService {

  private final TbUPbitKeyRepository keyRepository;
  private final PublicIpClient publicIpClient;
  private final UpbitClient upbitClient;

  public UPbitAccountService(
      TbUPbitKeyRepository keyRepository, PublicIpClient publicIpClient, UpbitClient upbitClient) {
    this.keyRepository = keyRepository;
    this.publicIpClient = publicIpClient;
    this.upbitClient = upbitClient;
  }

  @Transactional
  public void insertKey(UPbitKey key, String loginId) {
    Optional<TbUPbitKey> entity =
        keyRepository
            .findByUserLoginId(loginId)
            .map(
                e -> {
                  e.setAccessKey(key.getAccess());
                  e.setSecretKey(key.getSecret());
                  return e;
                });
    if (entity.isEmpty()) {
      keyRepository.save(key.toEntity(loginId));
    }
  }

  @Transactional
  public void updateAuto(String loginId, boolean auto) {
    keyRepository
        .findByUserLoginId(loginId)
        .map(
            e -> {
              e.setAutoOn(auto);
              return e;
            });
  }

  public boolean isAuto(String loginId) {
    return keyRepository.findByUserLoginId(loginId).map(TbUPbitKey::getAutoOn).orElse(false);
  }

  private Optional<UPbitKey> getKeyByLoginId(String loginId) {
    return keyRepository.findByUserLoginId(loginId).map(UPbitKey::fromEntity);
  }

  private String getAuthenticationToken(String loginId) {
    return getKeyByLoginId(loginId)
        .map(
            account -> {
              // JWT 생성
              Algorithm algorithm = Algorithm.HMAC256(account.getSecret());
              return JWT.create()
                  .withClaim("access_key", account.getAccess())
                  .withClaim("nonce", UUID.randomUUID().toString())
                  .sign(algorithm);
            })
        .orElse("");
  }

  private String getAuthenticationTokenForOrder(
      Map<String, String> params, String accessKey, String secretKey)
      throws NoSuchAlgorithmException {
    // 쿼리 해시 생성
    String queryString =
        params.entrySet().stream()
            .map(entry -> entry.getKey() + "=" + entry.getValue())
            .reduce((p1, p2) -> p1 + "&" + p2)
            .orElse("");

    MessageDigest md = MessageDigest.getInstance("SHA-512");
    md.update(queryString.getBytes(StandardCharsets.UTF_8));
    String queryHash = String.format("%0128x", new BigInteger(1, md.digest()));

    // JWT 토큰 생성
    Algorithm algorithm = Algorithm.HMAC256(secretKey);
    return getOrderToken(accessKey, algorithm, queryHash);
  }

  private String getAuthenticationTokenForOrderChance(
      String market, String accessKey, String secretKey) throws NoSuchAlgorithmException {
    // 1. Query Parameter 설정
    String queryString = "market=" + market;

    // 2. Query Hash 생성
    MessageDigest md = MessageDigest.getInstance("SHA-512");
    md.update(queryString.getBytes(StandardCharsets.UTF_8));
    String queryHash = String.format("%0128x", new BigInteger(1, md.digest()));

    // 3. JWT 토큰 생성
    Algorithm algorithm = Algorithm.HMAC256(secretKey);
    return getOrderToken(accessKey, algorithm, queryHash);
  }

  private String getOrderToken(String accessKey, Algorithm algorithm, String queryHash) {
    return JWT.create()
        .withClaim("access_key", accessKey)
        .withClaim("nonce", UUID.randomUUID().toString())
        .withClaim("query_hash", queryHash)
        .withClaim("query_hash_alg", "SHA512")
        .sign(algorithm);
  }

  /**
   * 전체 계좌 조회 GUIDE:
   * docs.upbit.com/reference/%EC%A0%84%EC%B2%B4-%EA%B3%84%EC%A2%8C-%EC%A1%B0%ED%9A%8C
   */
  @Transactional
  public List<UPbitAccount> getAccount(String loginId) {
    List<UPbitAccount> accounts = new ArrayList<>();

    String authenticationToken = getAuthenticationToken(loginId);

    if (authenticationToken.isEmpty()) return accounts;

    try {
      accounts = upbitClient.getAccount("Bearer " + authenticationToken);
    } catch (FeignException e) {
      int status = e.status();
      if (status == 401 || status == 403) {
        log.warn(
            "Upbit 인증/권한 오류로 자동매매를 해제합니다. loginId: {}, status: {}",
            loginId,
            status);
        keyRepository.findByUserLoginId(loginId).ifPresent(key -> key.setAutoOn(false));
      } else {
        log.warn(
            "Upbit 계좌 조회 HTTP 오류입니다. 자동매매는 유지합니다. loginId: {}, status: {}",
            loginId,
            status);
      }
    } catch (Exception e) {
      log.warn(
          "Upbit 계좌 조회 연결 오류입니다. 자동매매는 유지합니다. loginId: {}, error: {}",
          loginId,
          e.getClass().getSimpleName());
    }
    return accounts;
  }

  /**
   * 매수, 매도 주문하기 GUIDE: https://docs.upbit.com/reference/%EC%A3%BC%EB%AC%B8%ED%95%98%EA%B8%B0 시장가 매도
   * 매수 예정
   */
  public Optional<UPbitOrderResponse> order(
      String market, String priceOrVolume, String side, String accessKey, String secretKey) {
    // 요청 파라미터 설정
    Map<String, String> params = new HashMap<>();
    params.put("market", market);
    params.put("side", side); // 매수: bid, 매도: ask

    if ("bid".equals(side)) {
      params.put("price", priceOrVolume); // 시장가 매수 시 필수
      params.put("ord_type", "price");
    }
    if ("ask".equals(side)) {
      params.put("volume", priceOrVolume); // 시장가 매도 시 필수
      params.put("ord_type", "market");
    }

    // FeignClient를 통해 요청 전송
    try {
      String jwtToken = getAuthenticationTokenForOrder(params, accessKey, secretKey);
      String authenticationToken = "Bearer " + jwtToken;
      UPbitOrderResponse response = upbitClient.placeOrder(authenticationToken, params);
      log.info("Response: " + response);
      return Optional.ofNullable(response);
    } catch (NoSuchAlgorithmException e) {
      log.info("bid".equals(side) ? "매수 실패" : "매도 실패");
      return Optional.empty();
    }
  }

  /**
   * 주문-가능-정보 GUIDE:
   * https://docs.upbit.com/reference/%EC%A3%BC%EB%AC%B8-%EA%B0%80%EB%8A%A5-%EC%A0%95%EB%B3%B4
   */
  public UpbitOrderChanceResponse getOrdersChance(
      String accessKey, String secretKey, String market) {
    try {
      String jwtToken = getAuthenticationTokenForOrderChance(market, accessKey, secretKey);
      return upbitClient.getOrdersChance("Bearer " + jwtToken, market);
    } catch (NoSuchAlgorithmException ex) {
      throw new RuntimeException("API getOrdersChance Error!\n" + ex.getMessage());
    }
  }

  public String getIp() {
    try {
      return publicIpClient.getPublicIp();
    } catch (Exception e) {
      return "NOT FOUND IP";
    }
  }

  public List<TbUPbitKey> getAutoAccount() {
    return keyRepository.findAll().stream()
        .filter(TbUPbitKey::getAutoOn)
        .collect(Collectors.toList());
  }
}
