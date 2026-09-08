package com.uj.stxtory.service.order.upbit;

import com.uj.stxtory.domain.dto.upbit.UPbitAccount;
import com.uj.stxtory.domain.dto.upbit.UPbitInfo;
import com.uj.stxtory.domain.dto.upbit.UpbitOrderChanceResponse;
import com.uj.stxtory.domain.entity.TbUPbitKey;
import com.uj.stxtory.repository.UPbitOrderHistoryRepository;
import com.uj.stxtory.service.TradeErrorLogService;
import com.uj.stxtory.service.account.upbit.UPbitAccountService;
import com.uj.stxtory.service.calculation.CalculationClient;
import com.uj.stxtory.service.deal.notify.UPbitNotifyService;
import java.util.List;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Slf4j
@Service
public class UPbitOrderSchedulerService {

  private final UPbitAccountService accountService;
  private final UPbitNotifyService uPbitNotifyService;
  private final UPbitOrderHistoryRepository uPbitOrderHistoryRepository;
  private final TradeErrorLogService errorLogService;
  private final CalculationClient calculationClient;

  public UPbitOrderSchedulerService(
      UPbitAccountService accountService,
      UPbitNotifyService uPbitNotifyService,
      UPbitOrderHistoryRepository uPbitOrderHistoryRepository,
      TradeErrorLogService errorLogService,
      CalculationClient calculationClient) {
    this.accountService = accountService;
    this.uPbitNotifyService = uPbitNotifyService;
    this.uPbitOrderHistoryRepository = uPbitOrderHistoryRepository;
    this.errorLogService = errorLogService;
    this.calculationClient = calculationClient;
  }

  // 매매 스케쥴러
  @Scheduled(fixedDelay = 1000 * 30)
  public void upbitAutoOrder() {
    try {
      upbitAutoOrderInternal();
    } catch (Exception e) {
      log.error("Upbit 자동 주문 작업이 실패했습니다.", e);
      errorLogService.record("UPBIT", "AUTO_ORDER", e);
    }
  }

  private void upbitAutoOrderInternal() {
    List<String> markets =
        uPbitNotifyService.getSaved().stream().map(UPbitInfo::getCode).distinct().toList();
    accountService
        .getAutoAccount()
        .forEach(
            key -> {
              List<UPbitAccount> accounts = accountService.getAccount(key.getUserLoginId());
              if (accounts == null || accounts.isEmpty()) {
                log.info("Upbit 계좌를 조회할 수 없습니다. loginId: {}", key.getUserLoginId());
                return;
              }
              List<CalculationClient.TradeAction> actions =
                  calculationClient.decideAutoTrade(
                      markets, accounts.stream().map(UPbitAccount::getCurrency).toList());
              checkAndBuy(
                  key,
                  accounts,
                  actions.stream()
                      .filter(action -> "BUY".equals(action.side()))
                      .map(CalculationClient.TradeAction::market)
                      .toList());
              checkAndSale(
                  key,
                  accounts,
                  actions.stream()
                      .filter(action -> "SELL".equals(action.side()))
                      .map(CalculationClient.TradeAction::market)
                      .toList());
            });
  }

  // 매수부터 확인
  private void checkAndBuy(
      TbUPbitKey key, List<UPbitAccount> initialAccount, List<String> markets) {
    List<UPbitAccount> account = initialAccount;
    for (int i = 0; i < markets.size(); i++) {
      String m = markets.get(i);
      if (account == null || account.isEmpty()) return;
      // 현재 가진 돈
      double balance = Double.parseDouble(account.get(0).getBalance());
      UpbitOrderChanceResponse ordersChance =
          accountService.getOrdersChance(key.getAccessKey(), key.getSecretKey(), m);
      // 매수 수수료 비율
      double bidFee = Double.parseDouble(ordersChance.getBidFee());
      // 매수 요청 가격
      double dPrice = (1d - bidFee) * balance;
      String price = String.valueOf(dPrice);

      // 최소 주문 금액보다 크다면 주문
      if (dPrice > Double.parseDouble(ordersChance.getMarket().getBid().getMinTotal())) {
        accountService
            .order(m, price, "bid", key.getAccessKey(), key.getSecretKey())
            .map(o -> uPbitOrderHistoryRepository.save(o.toHistoryEntity(key.getUserLoginId())));
      }
      // 다음 종목 판단 전에는 주문 반영 후 잔고를 다시 조회한다.
      if (i + 1 < markets.size()) {
        account = accountService.getAccount(key.getUserLoginId());
      }
    }
  }

  private void checkAndSale(
      TbUPbitKey key, List<UPbitAccount> originalAccount, List<String> markets) {
    if (originalAccount == null || originalAccount.isEmpty()) return;
    List<UPbitAccount> account =
        originalAccount.stream()
            .filter(a -> !a.getCurrency().contains("KRW"))
            .collect(Collectors.toList());
    account.forEach(
        a -> {
          UpbitOrderChanceResponse ordersChance =
              accountService.getOrdersChance(
                  key.getAccessKey(), key.getSecretKey(), "KRW-" + a.getCurrency());
          String balance = ordersChance.getAskAccount().getBalance();
          if (markets.contains("KRW-" + a.getCurrency())) {
            accountService
                .order(
                    "KRW-" + a.getCurrency(),
                    balance,
                    "ask",
                    key.getAccessKey(),
                    key.getSecretKey())
                .map(
                    o -> uPbitOrderHistoryRepository.save(o.toHistoryEntity(key.getUserLoginId())));
          }
        });
  }
}
