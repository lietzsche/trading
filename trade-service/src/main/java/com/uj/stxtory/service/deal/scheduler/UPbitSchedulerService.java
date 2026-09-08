package com.uj.stxtory.service.deal.scheduler;

import com.uj.stxtory.service.DealSettingsService;
import com.uj.stxtory.service.TradeErrorLogService;
import com.uj.stxtory.service.deal.DealSchedulerService;
import com.uj.stxtory.service.deal.notify.UPbitNotifyService;
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
public class UPbitSchedulerService implements DealSchedulerService {
  private final MailService mailService;
  private final UPbitNotifyService uPbitNotifyService;
  private final DealSettingsService dealSettingsService;
  private final TradeErrorLogService errorLogService;

  public UPbitSchedulerService(
      MailService mailService,
      UPbitNotifyService uPbitNotifyService,
      DealSettingsService dealSettingsService,
      TradeErrorLogService errorLogService) {
    this.mailService = mailService;
    this.uPbitNotifyService = uPbitNotifyService;
    this.dealSettingsService = dealSettingsService;
    this.errorLogService = errorLogService;
  }

  // 매일 15분마다
  @Override
  @Scheduled(fixedRate = 1000 * 60 * 15)
  public void save() {
    execute(
        "SCHEDULE_SAVE",
        () -> {
          int baseDays = dealSettingsService.getByName("upbit").getHighestPriceReferenceDays();
          log.info("UPbit save start({})", baseDays);
          uPbitNotifyService.save();
          log.info("UPbit save async task submitted({})", baseDays);
        });
  }

  // 매일 1분마다
  @Override
  @Scheduled(fixedDelay = 1000 * 60)
  public void update() {
    execute(
        "SCHEDULE_UPDATE",
        () -> {
          log.info("UPbit update & mail send start");
          ApiUtil.runWithException(
              () -> mailService.noticeDelete(uPbitNotifyService.update().getDeleteItems(), "UPbit"));
          log.info("UPbit update & mail send complete");
        });
  }

  // 매일 정각마다
  @Override
  @Scheduled(cron = "0 0 * ? * *")
  public void mail() {
    execute(
        "SCHEDULE_MAIL",
        () -> {
          ApiUtil.runWithException(
              () -> mailService.noticeSelect(new ArrayList<>(uPbitNotifyService.getSaved()), "UPbit"));
          log.info("UPbit mail send complete");
        });
  }

  @Scheduled(cron = "0 30 17 * * *")
  public void saveHistory() {
    execute(
        "SCHEDULE_SAVE_HISTORY",
        () -> {
          log.info("upbit saveHistory start");
          uPbitNotifyService.saveHistory();
          log.info("upbit saveHistory async task submitted");
        });
  }

  private void execute(String operation, Runnable task) {
    try {
      task.run();
    } catch (Exception e) {
      log.error("Upbit 스케줄 작업이 실패했습니다. operation: {}", operation, e);
      errorLogService.record("UPBIT", operation, e);
    }
  }
}
