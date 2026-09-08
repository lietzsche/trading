package com.uj.stxtory.controller;

import com.uj.stxtory.service.deal.notify.StockNotifyService;
import com.uj.stxtory.service.deal.notify.UPbitNotifyService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Slf4j
public class CollectController {

  private final StockNotifyService stockNotifyService;
  private final UPbitNotifyService upbitNotifyService;

  public CollectController(
      StockNotifyService stockNotifyService, UPbitNotifyService upbitNotifyService) {
    this.stockNotifyService = stockNotifyService;
    this.upbitNotifyService = upbitNotifyService;
  }

  @GetMapping(value = "/collect/stock")
  public String stocksHistoryCollect() {
    log.info("\n\n\nstock saveHistory start\n\n\n");
    stockNotifyService.saveHistory();
    log.info("\n\n\nstock saveHistory complete\n\n\n");
    return "success";
  }

  @GetMapping(value = "/collect/upbit")
  public String upbitsHistoryCollect() {
    log.info("\n\n\nupbit saveHistory start\n\n\n");
    upbitNotifyService.saveHistory();
    log.info("\n\n\nupbit saveHistory complete\n\n\n");
    return "success";
  }
}
