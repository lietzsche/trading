package com.uj.stxtory.service.order.upbit;

import com.uj.stxtory.domain.dto.upbit.UPbitAccount;
import com.uj.stxtory.domain.dto.upbit.UPbitInfo;
import com.uj.stxtory.domain.dto.upbit.UpbitOrderChanceResponse;
import com.uj.stxtory.domain.entity.TbUPbitKey;
import com.uj.stxtory.repository.UPbitOrderHistoryRepository;
import com.uj.stxtory.service.TradeErrorLogService;
import com.uj.stxtory.service.account.upbit.UPbitAccountService;
import com.uj.stxtory.service.deal.notify.UPbitNotifyService;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
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

  public UPbitOrderSchedulerService(
      UPbitAccountService accountService,
      UPbitNotifyService uPbitNotifyService,
      UPbitOrderHistoryRepository uPbitOrderHistoryRepository,
      TradeErrorLogService errorLogService) {
    this.accountService = accountService;
    this.uPbitNotifyService = uPbitNotifyService;
    this.uPbitOrderHistoryRepository = uPbitOrderHistoryRepository;
    this.errorLogService = errorLogService;
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
    Map<Long, List<UPbitAccount>> accountsByKeyId = new HashMap<>();

    // 타입값 확인
    Map<Object, List<TbUPbitKey>> accountGroup =
        accountService.getAutoAccount().stream()
            .collect(
                Collectors.groupingBy(
                    key -> {
                      Optional<List<UPbitAccount>> account =
                          Optional.ofNullable(accountService.getAccount(key.getUserLoginId()));
                      account.ifPresent(value -> accountsByKeyId.put(key.getId(), value));
                      if (account.filter(a -> a.size() > 1).isPresent()) return "IN";
                      if (account.filter(a -> a.size() == 1).isPresent()) return "OUT";
                      return "NOT ACCOUNT";
                    }));

    Optional.ofNullable(accountGroup.get("NOT ACCOUNT"))
        .orElse(new ArrayList<>())
        .forEach(a -> log.info("Upbit 계좌를 조회할 수 없습니다. loginId: {}", a.getUserLoginId()));

    // 이미 가지고 있으니, 매도할지 판단 후 실행
    Optional.ofNullable(accountGroup.get("IN"))
        .map(
            in -> {
              in.forEach(key -> checkAndSale(key, accountsByKeyId.get(key.getId())));
              return true;
            });

    // 가지고 있는 게 없으니, 매수할지 판단 후 실행
    Optional.ofNullable(accountGroup.get("OUT"))
        .map(
            out -> {
              out.forEach(key -> checkAndBuy(key, accountsByKeyId.get(key.getId())));
              return true;
            });
  }

  // 매수부터 확인
  private void checkAndBuy(TbUPbitKey key, List<UPbitAccount> initialAccount) {
    List<String> markets =
        uPbitNotifyService.getSaved().stream().map(UPbitInfo::getCode).collect(Collectors.toList());
    if (markets.size() < 3) return;
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

  private void checkAndSale(TbUPbitKey key, List<UPbitAccount> originalAccount) {
    List<String> markets =
        uPbitNotifyService.getSaved().stream().map(UPbitInfo::getCode).collect(Collectors.toList());
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
          // 현재 추천 종목에 포함되지 않거나 추천 종목이 3개 미만이면 곧장 매도
          if (!markets.contains("KRW-" + a.getCurrency()) || markets.size() < 3) {
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
