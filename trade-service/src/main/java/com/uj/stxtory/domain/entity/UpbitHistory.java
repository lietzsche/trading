package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@Entity
@NoArgsConstructor
@AllArgsConstructor
public class UpbitHistory extends Base {
  @Id @GeneratedValue private Long id;

  @Column(name = "code", nullable = false)
  private String code;

  @Column(name = "name", nullable = false)
  private String name;

  /** 시가 */
  private double open;

  /** 현재가 */
  private double close;

  /** 고가 */
  private double high;

  /** 저가 */
  private double low;

  /** 일차이 */
  private double diff;

  /** 거래량 */
  private double volume;
}
