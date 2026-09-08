package com.uj.stxtory;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.dto.stock.StockModel;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class StxtoryApplicationTests {

  @Test
  void contextLoads() {}

  @Test
  void getStockInfo() {
    StockModel model = new StockModel(130);

    Map<String, List<DealPrice>> pricesMap =
        model.getAll().stream()
            //            .limit(5)
            .collect(Collectors.toMap(DealItem::getName, item -> model.getPrice(item, 130)));
    System.out.println(pricesMap);
  }
}
