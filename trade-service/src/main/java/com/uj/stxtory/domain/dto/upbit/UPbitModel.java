package com.uj.stxtory.domain.dto.upbit;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealModel;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import java.util.List;
import lombok.extern.slf4j.Slf4j;

@Slf4j
public class UPbitModel extends DealModel {

  int SEARCH_DAYS; // 6개월

  public UPbitModel(int daySize) {
    this.SEARCH_DAYS = daySize;
  }

  @Override
  public List<DealItem> getAll() {
    List<DealItem> coins = UPbitInfo.getAll();
    // 원화 기준만 취급
    return coins.stream().filter(c -> c.getCode().contains("KRW")).toList();
  }

  @Override
  public List<DealPrice> getPrice(DealItem item, int page) {
    return UPbitPriceInfo.getPriceInfoByDay(item.getCode(), SEARCH_DAYS);
  }
}
