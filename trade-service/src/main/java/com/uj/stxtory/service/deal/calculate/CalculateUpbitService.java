package com.uj.stxtory.service.deal.calculate;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.dto.upbit.UPbitModel;
import com.uj.stxtory.domain.entity.UpbitHistory;
import com.uj.stxtory.domain.entity.UpbitHistoryLabel;
import com.uj.stxtory.repository.UpbitHistoryLabelRepository;
import com.uj.stxtory.repository.UpbitHistoryRepository;
import com.uj.stxtory.util.FormatUtil;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class CalculateUpbitService {

  private final UpbitHistoryLabelRepository upbitHistoryLabelRepository;
  private final UpbitHistoryRepository upbitHistoryRepository;

  public CalculateUpbitService(
      UpbitHistoryLabelRepository upbitHistoryLabelRepository,
      UpbitHistoryRepository upbitHistoryRepository) {
    this.upbitHistoryLabelRepository = upbitHistoryLabelRepository;
    this.upbitHistoryRepository = upbitHistoryRepository;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void savePriceHistoryWithLabel(DealItem info, UPbitModel upbitModel) {
    boolean exist =
        upbitHistoryLabelRepository
            .findByCodeAndName(info.getCode(), info.getName())
            .map(
                label -> {
                  // 추가 저장은 label의 updatedAt 다음날부터
                  List<UpbitHistory> upbitHistories =
                      upbitModel.getPriceByPage(info, 1, 365).stream()
                          .filter(
                              p ->
                                  FormatUtil.dateToLocalDateTime(p.getDate()) != null
                                      && FormatUtil.dateToLocalDateTime(p.getDate())
                                          .isAfter(label.getUpdatedAt())
                                      && upbitHistoryRepository
                                          .findByCodeAndNameAndCreatedAt(
                                              info.getCode(),
                                              info.getName(),
                                              FormatUtil.dateToLocalDateTime(p.getDate()))
                                          .isEmpty())
                          .map(p -> getPriceHistory(info, p))
                          .distinct()
                          .toList();
                  upbitHistoryRepository.saveAll(upbitHistories);
                  label.setUpdatedAt(LocalDateTime.now());
                  return label;
                })
            .isPresent();
    if (!exist) {
      // 새로 저장은 1년
      List<UpbitHistory> upbitHistories =
          upbitModel.getPriceByPage(info, 1, 365).stream()
              .filter(p -> FormatUtil.dateToLocalDateTime(p.getDate()) != null)
              .map(p -> getPriceHistory(info, p))
              .distinct()
              .toList();
      UpbitHistoryLabel entity = new UpbitHistoryLabel(info.getCode(), info.getName());
      entity.setUpdatedAt(LocalDateTime.now());

      upbitHistoryRepository.saveAll(upbitHistories);
      upbitHistoryLabelRepository.save(entity);
    }
  }

  private UpbitHistory getPriceHistory(DealItem info, DealPrice p) {
    LocalDateTime createdAt = FormatUtil.dateToLocalDateTime(p.getDate());
    UpbitHistory history =
        UpbitHistory.builder()
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
