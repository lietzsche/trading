package com.uj.stxtory.domain.dto.deal;

import java.time.LocalDateTime;
import java.util.Date;
import java.util.List;

public interface DealItem {

  // 하한 및 기대 매도 가격 업데이트
  void sellingPriceUpdate(Date pricingDate, double highPer, double lowPer);

  String getCode();

  String getName();

  double getExpectedSellingPrice();

  double getMinimumSellingPrice();

  void setTempPrice(double price);

  void setSettingPrice(double price);

  double getTempPrice();

  double getSettingPrice();

  int getRenewalCnt();

  Object toEntity(double highPer, double lowPer);

  void setPrices(List<DealPrice> prices);

  LocalDateTime getPricingReferenceDate();
}
