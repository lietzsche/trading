package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import lombok.Data;

@Data
@Entity
public class UPbitOrderHistory extends Base {
  @Id @GeneratedValue private Long id;

  @Column(name = "login_id", nullable = false)
  private String loginId;

  private String uuid; // 주문의 고유 아이디
  private String side; // 주문 종류
  private String ordType; // 주문 방식
  private String price; // 주문 당시 화폐 가격
  private String state; // 주문 상태
  private String market; // 마켓의 유일키
  private String volume; // 사용자가 입력한 주문 양
  private String remainingVolume; // 체결 후 남은 주문 양
  private String reservedFee; // 수수료로 예약된 비용
  private String remainingFee; // 남은 수수료
  private String paidFee; // 사용된 수수료
  private String locked; // 거래에 사용중인 비용
  private String executedVolume; // 체결된 양
  private Integer tradesCount; // 해당 주문에 걸린 체결 수
  private String timeInForce; // IOC, FOK 설정
  private String identifier;
}
