package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import java.time.LocalDate;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Builder
@Data
@Entity
@NoArgsConstructor
@AllArgsConstructor
public class DividendStock extends Base {
  @Id @GeneratedValue private Long id;

  @Column(name = "code", nullable = false)
  private String code;

  @Column(name = "name", nullable = false)
  private String name;

  @Column(name = "dividend_rate", nullable = false)
  private Double dividendRate;

  @Column(name = "ex_div_date")
  private LocalDate exDivDate; // 배당락일

  @Column(name = "pay_date")
  private LocalDate payDate; // 지급일

  public static DividendStock of(
      String code, String name, Double dividendRate, LocalDate exDivDate, LocalDate payDate) {
    if (code == null || name == null || dividendRate == null) return null;
    return DividendStock.builder()
        .code(code)
        .name(name)
        .dividendRate(dividendRate)
        .exDivDate(exDivDate)
        .payDate(payDate)
        .build();
  }

  public boolean valueEquals(DividendStock ds) {
    return this.dividendRate.equals(ds.getDividendRate())
        && this.exDivDate.equals(ds.getExDivDate())
        && this.payDate.equals(ds.getPayDate());
  }
}
