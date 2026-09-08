package com.uj.stxtory.service.deal.calculate;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.dto.stock.StockModel;
import com.uj.stxtory.domain.entity.StockHistory;
import com.uj.stxtory.domain.entity.StockHistoryLabel;
import com.uj.stxtory.repository.StockHistoryLabelRepository;
import com.uj.stxtory.repository.StockHistoryRepository;
import com.uj.stxtory.util.FormatUtil;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class CalculateStockService {

  private final StockHistoryLabelRepository stockHistoryLabelRepository;
  private final StockHistoryRepository stockHistoryRepository;

  public CalculateStockService(
      StockHistoryLabelRepository stockHistoryLabelRepository,
      StockHistoryRepository stockHistoryRepository) {
    this.stockHistoryLabelRepository = stockHistoryLabelRepository;
    this.stockHistoryRepository = stockHistoryRepository;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void savePriceHistoryWithLabel(DealItem info, StockModel stockModel) {
    boolean exist =
        stockHistoryLabelRepository
            .findByCodeAndName(info.getCode(), info.getName())
            .map(
                label -> {
                  // 추가 저장은 label의 updatedAt 다음날부터
                  List<StockHistory> stockHistories =
                      stockModel.getPriceByPage(info, 1, 130).stream()
                          .filter(
                              p ->
                                  FormatUtil.dateToLocalDateTime(p.getDate()) != null
                                      && FormatUtil.dateToLocalDateTime(p.getDate())
                                          .isAfter(label.getUpdatedAt())
                                      && stockHistoryRepository
                                          .findByCodeAndNameAndCreatedAt(
                                              info.getCode(),
                                              info.getName(),
                                              FormatUtil.dateToLocalDateTime(p.getDate()))
                                          .isEmpty())
                          .map(p -> getPriceHistory(info, p))
                          .distinct()
                          .toList();
                  if (stockHistories.isEmpty()) return label;
                  stockHistoryRepository.saveAll(stockHistories);
                  label.setUpdatedAt(LocalDateTime.now());
                  return label;
                })
            .isPresent();
    if (!exist) {
      // 새로 저장은 1년
      List<StockHistory> stockHistories =
          stockModel.getPriceByPage(info, 1, 130).stream()
              .filter(p -> FormatUtil.dateToLocalDateTime(p.getDate()) != null)
              .map(p -> getPriceHistory(info, p))
              .distinct()
              .toList();
      if (stockHistories.isEmpty()) return;
      StockHistoryLabel entity = new StockHistoryLabel(info.getCode(), info.getName());
      entity.setUpdatedAt(LocalDateTime.now());

      stockHistoryRepository.saveAll(stockHistories);
      stockHistoryLabelRepository.save(entity);
    }
  }

  private StockHistory getPriceHistory(DealItem info, DealPrice p) {
    LocalDateTime createdAt = FormatUtil.dateToLocalDateTime(p.getDate());
    StockHistory history =
        StockHistory.builder()
            .name(info.getName())
            .code(info.getCode())
            .low(p.getLow())
            .high(p.getHigh())
            .open(p.getOpen())
            .close(p.getClose())
            .diff(p.getDiff())
            .volume(p.getVolume())
            .build();
    history.setCreatedAt(createdAt);
    return history;
  }
}
