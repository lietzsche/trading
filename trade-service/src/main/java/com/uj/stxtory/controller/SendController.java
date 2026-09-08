package com.uj.stxtory.controller;

import com.uj.stxtory.domain.dto.stock.StockInfo;
import com.uj.stxtory.domain.dto.upbit.UPbitInfo;
import com.uj.stxtory.service.deal.notify.StockNotifyService;
import com.uj.stxtory.service.deal.notify.UPbitNotifyService;
import com.uj.stxtory.service.mail.MailService;
import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class SendController {

  @Autowired MailService mailService;
  @Autowired StockNotifyService stockNotifyService;
  @Autowired UPbitNotifyService uPbitNotifyService;

  @ResponseBody
  @GetMapping("/stock")
  public boolean stock() {
    List<StockInfo> all = stockNotifyService.getSaved();
    mailService.noticeSelect(new ArrayList<>(all), "STOCK");
    return true;
  }

  @ResponseBody
  @GetMapping("/upbit")
  public boolean upbit() {
    List<UPbitInfo> all = uPbitNotifyService.getSaved();
    mailService.noticeSelect(new ArrayList<>(all), "UPbit");
    return true;
  }
}
