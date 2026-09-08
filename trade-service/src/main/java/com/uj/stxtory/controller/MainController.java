package com.uj.stxtory.controller;

import com.uj.stxtory.domain.entity.TbUPbitKey;
import com.uj.stxtory.repository.TbUPbitKeyRepository;
import com.uj.stxtory.service.deal.notify.StockNotifyService;
import com.uj.stxtory.service.deal.notify.UPbitNotifyService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
@Slf4j
public class MainController {
  private final StockNotifyService stockNotifyService;
  private final UPbitNotifyService uPbitNotifyService;
  private final TbUPbitKeyRepository tbUPbitKeyRepository;

  public MainController(
      StockNotifyService stockNotifyService,
      UPbitNotifyService uPbitNotifyService,
      TbUPbitKeyRepository tbUPbitKeyRepository) {
    this.stockNotifyService = stockNotifyService;
    this.uPbitNotifyService = uPbitNotifyService;
    this.tbUPbitKeyRepository = tbUPbitKeyRepository;
  }

  @GetMapping(value = "/")
  public String mainPage(@AuthenticationPrincipal String loginId) {
    if (tbUPbitKeyRepository.findByUserLoginId(loginId).filter(TbUPbitKey::getAutoOn).isPresent())
      return "redirect:/select/upbit";
    return "main";
  }

  @GetMapping(value = "/select/stock")
  public String stocks(Model model) {
    model.addAttribute("items", stockNotifyService.getSaved());
    return "stock";
  }

  @GetMapping(value = "/select/upbit")
  public String upbits(Model model) {
    model.addAttribute("items", uPbitNotifyService.getSaved());
    return "upbit";
  }

  @GetMapping(value = "/select/dividend/stock")
  public String dividends(Model model) {
    model.addAttribute("items", stockNotifyService.getSavedDividendStocks());
    return "customStock";
  }
}
