package com.uj.stxtory.domain.entity;

import com.fasterxml.jackson.annotation.JsonFormat;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Entity
@NoArgsConstructor
@AllArgsConstructor
public class UPbit extends Base {
  @Id @GeneratedValue private Long id;

  @Column(name = "code", nullable = false)
  private String code;

  @Column(name = "name", nullable = false)
  private String name;

  /** 타깃 최초 하한 매도 가격 */
  @Column(name = "origin_minimum_selling_price", nullable = false)
  private double originMinimumSellingPrice;

  /** 타깃 최초 기대 매도 가격 */
  @Column(name = "origin_expected_selling_price", nullable = false)
  private double originExpectedSellingPrice;

  /** 타깃 하한 매도 가격 */
  @Column(name = "minimum_selling_price", nullable = false)
  private double minimumSellingPrice;

  /** 타깃 기대 매도 가격 */
  @Column(name = "expected_selling_price", nullable = false)
  private double expectedSellingPrice;

  /** 타깃 실시간 가격 */
  @Column(name = "temp_price", nullable = false)
  private double tempPrice;

  /** 타깃 설정시 가격 */
  @Column(name = "setting_price", nullable = false)
  private double settingPrice;

  /** 가격 설정 기준 날짜 */
  @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "Asia/Seoul")
  @Column(name = "pricing_reference_date", nullable = true)
  private LocalDateTime pricingReferenceDate = LocalDateTime.now();

  /** 갱신 횟수 */
  @Column(name = "renewal_cnt", nullable = false)
  private int renewalCnt;

  public UPbit(
      String code,
      String name,
      double originMinimumSellingPrice,
      double originExpectedSellingPrice,
      double minimumSellingPrice,
      double expectedSellingPrice,
      double tempPrice,
      double settingPrice) {
    this.code = code;
    this.name = name;
    this.originMinimumSellingPrice = originMinimumSellingPrice;
    this.originExpectedSellingPrice = originExpectedSellingPrice;
    this.minimumSellingPrice = minimumSellingPrice;
    this.expectedSellingPrice = expectedSellingPrice;
    this.tempPrice = tempPrice;
    this.settingPrice = settingPrice;
    this.renewalCnt = 0;
    // 날짜만 남기고 나머지 오후 5시로 설정
    this.setCreatedAt(LocalDateTime.now());
  }
}
