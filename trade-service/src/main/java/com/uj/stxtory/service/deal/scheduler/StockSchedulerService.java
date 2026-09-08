package com.uj.stxtory.service.deal.scheduler;

import com.uj.stxtory.service.DealSettingsService;
import com.uj.stxtory.service.TradeErrorLogService;
import com.uj.stxtory.service.deal.DealSchedulerService;
import com.uj.stxtory.service.deal.notify.StockNotifyService;
import com.uj.stxtory.service.mail.MailService;
import com.uj.stxtory.util.ApiUtil;
import java.util.ArrayList;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Transactional
@Service
public class StockSchedulerService implements DealSchedulerService {
  private final MailService mailService;
  private final StockNotifyService stockNotifyService;
  private final DealSettingsService dealSettingsService;
  private final TradeErrorLogService errorLogService;

  public StockSchedulerService(
      MailService mailService,
      StockNotifyService stockNotifyService,
      DealSettingsService dealSettingsService,
      TradeErrorLogService errorLogService) {
    this.mailService = mailService;
    this.stockNotifyService = stockNotifyService;
    this.dealSettingsService = dealSettingsService;
    this.errorLogService = errorLogService;
  }

  // 월-금 아침 8시 - 오후 4시: 정각 및 20분, 40분 마다
  @Override
  @Scheduled(cron = "0 0/15 8-16 ? * MON-FRI")
  public void save() {
    execute(
        "SCHEDULE_SAVE",
        () -> {
          int baseDays = dealSettingsService.getByName("stock").getHighestPriceReferenceDays();
          log.info("stock save start({})", baseDays);
          stockNotifyService.save();
          log.info("stock save async task submitted({})", baseDays);
        });
  }

  // 월-금 아침 8시 - 오후 3시 59분: 1분 마다
  @Override
  @Scheduled(cron = "0 * 8-15 ? * MON-FRI")
  public void update() {
    execute(
        "SCHEDULE_UPDATE",
        () -> {
          log.info("stock update & mail send start");
          ApiUtil.runWithException(
              () -> mailService.noticeDelete(stockNotifyService.update().getDeleteItems(), "STOCK"));
          log.info("stock update & mail send complete");
        });
  }

  // 월-금 아침 8시 - 오후 4시: 정각 마다
  @Override
  @Scheduled(cron = "0 0 8-16 ? * MON-FRI")
  public void mail() {
    execute(
        "SCHEDULE_MAIL",
        () -> {
          ApiUtil.runWithException(
              () -> mailService.noticeSelect(new ArrayList<>(stockNotifyService.getSaved()), "STOCK"));
          log.info("STOCK mail send complete");
        });
  }

  @Scheduled(cron = "0 30 17 * * *")
  public void saveHistory() {
    execute(
        "SCHEDULE_SAVE_HISTORY",
        () -> {
          log.info("stock saveHistory start");
          stockNotifyService.saveHistory();
          log.info("stock saveHistory async task submitted");
        });
  }

  @Scheduled(cron = "0 30 17 * * *")
  public void saveDividendStocks() {
    execute(
        "SCHEDULE_SAVE_DIVIDEND_STOCKS",
        () -> {
          log.info("stock saveDividendStocks start");
          stockNotifyService.saveDividendStocks();
          log.info("stock saveDividendStocks async task submitted");
        });
  }

  private void execute(String operation, Runnable task) {
    try {
      task.run();
    } catch (Exception e) {
      log.error("주식 스케줄 작업이 실패했습니다. operation: {}", operation, e);
      errorLogService.record("STOCK", operation, e);
    }
  }
}
