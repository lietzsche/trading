package com.uj.stxtory.domain.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Entity
@NoArgsConstructor
@AllArgsConstructor
public class DealSettings extends Base {
  @Id @GeneratedValue private Long id;
  private String name;
  private Long expectedHighPercentage;
  private Long expectedLowPercentage;
  private int highestPriceReferenceDays; // 신고가 기준일 수
  private boolean isVolumeCheck;
}
