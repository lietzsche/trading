package com.uj.stxtory.domain.dto.upbit;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.uj.stxtory.domain.entity.UPbitOrderHistory;
import lombok.Data;

@Data
public class UPbitOrderResponse {
  private String uuid; // 주문의 고유 아이디
  private String side; // 주문 종류

  @JsonProperty("ord_type")
  private String ordType; // 주문 방식

  private String price; // 주문 당시 화폐 가격
  private String state; // 주문 상태
  private String market; // 마켓의 유일키

  @JsonProperty("created_at")
  private String createdAt; // 주문 생성 시간

  private String volume; // 사용자가 입력한 주문 양

  @JsonProperty("remaining_volume")
  private String remainingVolume; // 체결 후 남은 주문 양

  @JsonProperty("reserved_fee")
  private String reservedFee; // 수수료로 예약된 비용

  @JsonProperty("remaining_fee")
  private String remainingFee; // 남은 수수료

  @JsonProperty("paid_fee")
  private String paidFee; // 사용된 수수료

  private String locked; // 거래에 사용중인 비용

  @JsonProperty("executed_volume")
  private String executedVolume; // 체결된 양

  @JsonProperty("trades_count")
  private Integer tradesCount; // 해당 주문에 걸린 체결 수

  @JsonProperty("time_in_force")
  private String timeInForce; // IOC, FOK 설정

  private String identifier;

  public UPbitOrderHistory toHistoryEntity(String loginId) {
    UPbitOrderHistory entity = new UPbitOrderHistory();
    entity.setLoginId(loginId);
    entity.setUuid(this.uuid);
    entity.setSide(this.side);
    entity.setOrdType(this.ordType);
    entity.setPrice(this.price);
    entity.setState(this.state);
    entity.setMarket(this.market);
    entity.setVolume(this.volume);
    entity.setRemainingVolume(this.remainingVolume);
    entity.setReservedFee(this.reservedFee);
    entity.setRemainingFee(this.remainingFee);
    entity.setPaidFee(this.paidFee);
    entity.setLocked(this.locked);
    entity.setExecutedVolume(this.executedVolume);
    entity.setTradesCount(this.tradesCount);
    entity.setTimeInForce(this.timeInForce);
    entity.setIdentifier(this.identifier);
    return entity;
  }
}
