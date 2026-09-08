package com.uj.stxtory.domain.dto.upbit;

import lombok.Data;

@Data
public class UPbitAccount {
  private String currency;
  private String balance;
  private String locked;
  private String avgBuyPrice;
  private boolean avgBuyPriceModified;
  private String unitCurrency;
}
