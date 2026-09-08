package com.uj.stxtory.service.deal.scheduler;

import com.uj.stxtory.service.DealSettingsService;
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

  public StockSchedulerService(
      MailService mailService,
      StockNotifyService stockNotifyService,
      DealSettingsService dealSettingsService) {
    this.mailService = mailService;
    this.stockNotifyService = stockNotifyService;
    this.dealSettingsService = dealSettingsService;
  }

  // 월-금 아침 8시 - 오후 4시: 정각 및 20분, 40분 마다
  @Override
  @Scheduled(cron = "0 0/15 8-16 ? * MON-FRI")
  public void save() {
    int baseDays = dealSettingsService.getByName("stock").getHighestPriceReferenceDays();
    log.info("\n\n\nstock save start(" + baseDays + ")\n\n\n");
    stockNotifyService.save();
    log.info("stock save async task submitted({})", baseDays);
  }

  // 월-금 아침 8시 - 오후 3시 59분: 1분 마다
  @Override
  @Scheduled(cron = "0 * 8-15 ? * MON-FRI")
  public void update() {
    log.info("\n\n\nstock update & mail send start\n\n\n");
    ApiUtil.runWithException(
        () -> mailService.noticeDelete(stockNotifyService.update().getDeleteItems(), "STOCK"));
    log.info("\n\n\nstock update & mail send complete\n\n\n");
  }

  // 월-금 아침 8시 - 오후 4시: 정각 마다
  @Override
  @Scheduled(cron = "0 0 8-16 ? * MON-FRI")
  public void mail() {
    ApiUtil.runWithException(
        () -> mailService.noticeSelect(new ArrayList<>(stockNotifyService.getSaved()), "STOCK"));
    log.info("\n\n\nSTOCK mail send Complete\n\n\n");
  }

  @Scheduled(cron = "0 30 17 * * *")
  public void saveHistory() {
    log.info("\n\n\nstock saveHistory start\n\n\n");
    stockNotifyService.saveHistory();
    log.info("stock saveHistory async task submitted");
  }

  @Scheduled(cron = "0 30 17 * * *")
  public void saveDividendStocks() {
    log.info("\n\n\nstock saveDividendStocks start\n\n\n");
    stockNotifyService.saveDividendStocks();
    log.info("stock saveDividendStocks async task submitted");
  }
}
