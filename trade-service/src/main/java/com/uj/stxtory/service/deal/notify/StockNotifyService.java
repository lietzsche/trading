package com.uj.stxtory.service.deal.notify;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealModel;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.dto.deal.DealSettingsInfo;
import com.uj.stxtory.domain.dto.stock.DividendStockInfo;
import com.uj.stxtory.domain.dto.stock.StockInfo;
import com.uj.stxtory.domain.dto.stock.StockModel;
import com.uj.stxtory.domain.dto.stock.StockPriceInfo;
import com.uj.stxtory.domain.entity.DividendStock;
import com.uj.stxtory.domain.entity.Stock;
import com.uj.stxtory.domain.entity.StockHistory;
import com.uj.stxtory.repository.DividendStockRepository;
import com.uj.stxtory.repository.StockHistoryRepository;
import com.uj.stxtory.repository.StockRepository;
import com.uj.stxtory.service.DealSettingsService;
import com.uj.stxtory.service.TradeErrorLogService;
import com.uj.stxtory.service.deal.DealNotifyService;
import com.uj.stxtory.service.deal.calculate.CalculateStockService;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.*;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Transactional
@Service
@Slf4j
public class StockNotifyService implements DealNotifyService {

  private static final String SETTING_NAME = "stock";

  private final StockRepository stockRepository;
  private final StockHistoryRepository stockHistoryRepository;
  private final DealSettingsService dealSettingsService;
  private final CalculateStockService calculateStockService;
  private final DividendStockRepository dividendStockRepository;
  private final TradeErrorLogService errorLogService;

  public StockNotifyService(
      StockRepository stockRepository,
      DealSettingsService dealSettingsService,
      CalculateStockService calculStockService,
      StockHistoryRepository stockHistoryRepository,
      DividendStockRepository dividendStockRepository,
      TradeErrorLogService errorLogService) {
    this.stockRepository = stockRepository;
    this.dealSettingsService = dealSettingsService;
    this.calculateStockService = calculStockService;
    this.stockHistoryRepository = stockHistoryRepository;
    this.dividendStockRepository = dividendStockRepository;
    this.errorLogService = errorLogService;
  }

  public List<StockInfo> getSaved() {
    return callSaved().stream().map(StockInfo::fromEntity).toList();
  }

  private List<Stock> callSaved() { // 목표가와 현재가가 비율 상으로 가장 가까운 순
    return stockRepository.findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc().stream()
        .filter(s -> s.getExpectedSellingPrice() != s.getMinimumSellingPrice())
        .sorted(
            Comparator.comparing(Stock::getRenewalCnt)
                .reversed()
                .thenComparingDouble(
                    s ->
                        (s.getExpectedSellingPrice() - s.getTempPrice())
                            / (s.getExpectedSellingPrice() - s.getMinimumSellingPrice())))
        .toList();
  }

  public static void main(String[] args) {
    int page = 13;
    String stockCode = "033240";
    long highPer = 10L;
    long lowPer = -5L;

    List<DealPrice> priceInfos = StockPriceInfo.getPriceInfoByPage(stockCode, 1, page);

    Map<String, List<DealPrice>> map = Map.of(stockCode, priceInfos);

    StockModel model = new StockModel(page);
    model.calculateByThreeDaysByPageForSaveByDatabase(lowPer, highPer, map, true);
  }

  @Async
  @Override
  public void save() {
    log.info("stock save async task started");
    try {
      saveInternal();
      log.info("stock save async task completed");
    } catch (Exception e) {
      log.error("stock save async task failed", e);
      errorLogService.record("STOCK", "SAVE", e);
      throw new IllegalStateException("stock save async task failed", e);
    }
  }

  private void saveInternal() {
    List<Stock> saved = callSaved();

    DealSettingsInfo settings = dealSettingsService.getByName(SETTING_NAME);
    StockModel stockModel = new StockModel(settings.getHighestPriceReferenceDays());

    List<DealItem> saveItems =
        stockModel.calculateByThreeDaysByPageForSaveByDatabase(
            (double) settings.getExpectedLowPercentage(),
            (double) settings.getExpectedHighPercentage(),
            getPricesMap(stockModel, settings),
            settings.isVolumeCheck());

    List<Stock> save =
        saveItems.stream()
            .filter(item -> saved.stream().noneMatch(s -> s.getCode().equals(item.getCode())))
            .map(
                item ->
                    (Stock)
                        item.toEntity(
                            1 + ((double) settings.getExpectedHighPercentage() / 100),
                            1 + ((double) settings.getExpectedLowPercentage() / 100)))
            .toList();
    stockRepository.saveAll(save);

    // 외부 조회 결과에서 빠졌다는 이유만으로 기존 종목을 삭제하지 않는다.
    // 실제 매도 조건에 따른 삭제는 update()에서만 수행한다.
  }

  @Override
  public DealModel update() {
    List<Stock> saved = callSaved();

    List<DealItem> items = saved.stream().map(StockInfo::fromEntity).collect(Collectors.toList());

    DealSettingsInfo settings = dealSettingsService.getByName(SETTING_NAME);

    DealModel model = new StockModel(settings.getHighestPriceReferenceDays());

    if (saved.isEmpty()) return model;
    model.calculateForTodayUpdateByDatabase(
        items,
        getPricesMap(items, model, settings),
        1 + ((double) settings.getExpectedHighPercentage() / 100),
        1 + ((double) settings.getExpectedLowPercentage() / 100));
    List<DealItem> updateItems = model.getNowItems();
    List<DealItem> deleteItems = model.getDeleteItems();

    update(saved, updateItems);
    delete(saved, deleteItems);

    return model;
  }

  private Map<String, List<DealPrice>> getPricesMap(
      List<DealItem> items, DealModel model, DealSettingsInfo settings) {
    Map<String, List<DealPrice>> pricesMap = new HashMap<>();
    items.forEach(
        item -> {
          List<StockPriceInfo> historyPrices =
              stockHistoryRepository.findByCode(item.getCode()).stream()
                  .map(
                      history ->
                          new StockPriceInfo(
                              Date.from(
                                  history
                                      .getCreatedAt()
                                      .atZone(ZoneId.systemDefault())
                                      .toInstant()),
                              history.getClose(),
                              history.getDiff(),
                              history.getOpen(),
                              history.getHigh(),
                              history.getLow(),
                              history.getVolume()))
                  .toList();
          List<DealPrice> currentPrices = model.getPrice(item, 1);
          if (currentPrices.isEmpty()) {
            throw new IllegalStateException("현재 주식 가격이 비어 있습니다. code: " + item.getCode());
          }
          ArrayList<DealPrice> prices = new ArrayList<>(historyPrices);
          prices.addAll(currentPrices);
          pricesMap.put(
              item.getCode(),
              prices.stream()
                  .filter(p -> p.getDate() != null)
                  .distinct()
                  .sorted((prev, curr) -> curr.getDate().compareTo(prev.getDate()))
                  .limit(settings.getHighestPriceReferenceDays())
                  .toList());
        });

    return pricesMap;
  }

  private Map<String, List<DealPrice>> getPricesMap(DealModel model, DealSettingsInfo settings) {
    Map<String, List<DealPrice>> pricesMap = new HashMap<>();

    Map<String, List<StockHistory>> historyMap =
        stockHistoryRepository.findByCreatedAtAfter(LocalDateTime.now().minusYears(1)).stream()
            .collect(Collectors.groupingBy(StockHistory::getCode));
    historyMap.forEach(
        (code, histories) -> {
          List<StockPriceInfo> historyPrices =
              histories.stream()
                  .map(
                      history ->
                          new StockPriceInfo(
                              Date.from(
                                  history
                                      .getCreatedAt()
                                      .atZone(ZoneId.systemDefault())
                                      .toInstant()),
                              history.getClose(),
                              history.getDiff(),
                              history.getOpen(),
                              history.getHigh(),
                              history.getLow(),
                              history.getVolume()))
                  .toList();
          StockInfo item = new StockInfo();
          item.setCode(code);
          List<DealPrice> currentPrices = model.getPrice(item, 1);
          if (currentPrices.isEmpty()) {
            throw new IllegalStateException("현재 주식 가격이 비어 있습니다. code: " + item.getCode());
          }
          ArrayList<DealPrice> prices = new ArrayList<>(historyPrices);
          prices.addAll(currentPrices);
          pricesMap.put(
              item.getCode(),
              prices.stream()
                  .filter(p -> p.getDate() != null)
                  .distinct()
                  .sorted((prev, curr) -> curr.getDate().compareTo(prev.getDate()))
                  .limit(settings.getHighestPriceReferenceDays())
                  .toList());
        });

    return pricesMap;
  }

  private void update(List<Stock> saved, List<DealItem> updateItems) {
    saved.forEach(
        stock ->
            updateItems.stream()
                .filter(pItem -> pItem.getCode().equals(stock.getCode()))
                .findFirst()
                .map(
                    item -> {
                      stock.setPricingReferenceDate(item.getPricingReferenceDate());
                      stock.setExpectedSellingPrice(item.getExpectedSellingPrice());
                      stock.setMinimumSellingPrice(item.getMinimumSellingPrice());
                      stock.setRenewalCnt(item.getRenewalCnt());
                      stock.setTempPrice(item.getTempPrice());
                      stock.setSettingPrice(item.getSettingPrice());
                      stock.setUpdatedAt(LocalDateTime.now());
                      return stock;
                    }));
  }

  private void delete(List<Stock> saved, List<DealItem> deleteItems) {
    saved.forEach(
        stock ->
            deleteItems.stream()
                .filter(pItem -> pItem.getCode().equals(stock.getCode()))
                .findFirst()
                .map(
                    item -> {
                      stock.setDeletedAt(LocalDateTime.now());
                      return stock;
                    }));
  }

  @Override
  @Async
  public void saveHistory() {
    log.info("stock saveHistory async task started");
    try {
      saveHistoryInternal();
      log.info("stock saveHistory async task completed");
    } catch (Exception e) {
      log.error("stock saveHistory async task failed", e);
      errorLogService.record("STOCK", "SAVE_HISTORY", e);
      throw new IllegalStateException("stock saveHistory async task failed", e);
    }
  }

  private void saveHistoryInternal() {
    DealSettingsInfo settings = dealSettingsService.getByName(SETTING_NAME);
    StockModel stockModel = new StockModel(settings.getHighestPriceReferenceDays());

    // 저장로직
    stockModel
        .getAll()
        .forEach(info -> calculateStockService.savePriceHistoryWithLabel(info, stockModel));
  }

  public List<DividendStockInfo> getSavedDividendStocks() {
    return dividendStockRepository.findAllByDeletedAtIsNullOrderByDividendRateDesc().stream()
        .map(DividendStockInfo::fromEntity)
        // 추후 배당락일과 지급일이 설정된 종목이 우선 보여야 할 때 수정(현재 크롤링해서 가져오는 배당락일과 지급일이 유효하지 않음)
        //        .sorted(
        //            Comparator.comparing(
        //                    (DividendStockInfo s) -> s.getExDivDate() != null || s.getPayDate() !=
        // null)
        //                .reversed()
        //                .thenComparing(
        //                    DividendStockInfo::getDividendRate,
        //                    Comparator.nullsLast(Comparator.reverseOrder())))
        .toList();
  }

  @Async
  public void saveDividendStocks() {
    log.info("stock saveDividendStocks async task started");
    try {
      saveDividendStocksInternal();
      log.info("stock saveDividendStocks async task completed");
    } catch (Exception e) {
      log.error("stock saveDividendStocks async task failed", e);
      errorLogService.record("STOCK", "SAVE_DIVIDEND_STOCKS", e);
      throw new IllegalStateException("stock saveDividendStocks async task failed", e);
    }
  }

  private void saveDividendStocksInternal() {
    List<DividendStock> items = DividendStockInfo.getDividendStocks();

    // 기존 히스토리 있으면, 비교 후 모든 값이 같으면 삭제
    items =
        items.stream()
            .filter(
                item -> {
                  Optional<DividendStock> optional =
                      dividendStockRepository.findByCodeAndDeletedAtIsNull(item.getCode());
                  if (optional.isPresent()) {
                    DividendStock ds = optional.get();
                    if (item.valueEquals(ds)) return false;
                    else {
                      ds.setDeletedAt(LocalDateTime.now());
                    }
                  }
                  return true;
                })
            .toList();

    // 저장
    dividendStockRepository.saveAll(items);
  }
}
