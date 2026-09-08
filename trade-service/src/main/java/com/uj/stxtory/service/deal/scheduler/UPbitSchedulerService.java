package com.uj.stxtory.service.deal.scheduler;

import com.uj.stxtory.service.DealSettingsService;
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

  public UPbitSchedulerService(
      MailService mailService,
      UPbitNotifyService uPbitNotifyService,
      DealSettingsService dealSettingsService) {
    this.mailService = mailService;
    this.uPbitNotifyService = uPbitNotifyService;
    this.dealSettingsService = dealSettingsService;
  }

  // 매일 15분마다
  @Override
  @Scheduled(fixedRate = 1000 * 60 * 15)
  public void save() {
    int baseDays = dealSettingsService.getByName("upbit").getHighestPriceReferenceDays();
    log.info("\n\n\nUPbit save start(" + baseDays + ")\n\n\n");
    uPbitNotifyService.save();
    log.info("\n\n\nUPbit save complete(" + baseDays + ")\n\n\n");
  }

  // 매일 1분마다
  @Override
  @Scheduled(fixedDelay = 1000 * 60)
  public void update() {
    log.info("\n\n\nUPbit update & mail send start\n\n\n");
    ApiUtil.runWithException(
        () -> mailService.noticeDelete(uPbitNotifyService.update().getDeleteItems(), "UPbit"));
    log.info("\n\n\nUPbit update & mail send complete\n\n\n");
  }

  // 매일 정각마다
  @Override
  @Scheduled(cron = "0 0 * ? * *")
  public void mail() {
    ApiUtil.runWithException(
        () -> mailService.noticeSelect(new ArrayList<>(uPbitNotifyService.getSaved()), "UPbit"));
    log.info("\n\n\nUPbit mail send Complete\n\n\n");
  }

  @Scheduled(cron = "0 30 17 * * *")
  public void saveHistory() {
    log.info("\n\n\nupbit saveHistory start\n\n\n");
    uPbitNotifyService.saveHistory();
    log.info("\n\n\nupbit saveHistory complete\n\n\n");
  }
}
