package com.uj.stxtory.service.deal.notify;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealModel;
import com.uj.stxtory.domain.dto.deal.DealSettingsInfo;
import com.uj.stxtory.domain.dto.upbit.UPbitInfo;
import com.uj.stxtory.domain.dto.upbit.UPbitModel;
import com.uj.stxtory.domain.entity.UPbit;
import com.uj.stxtory.repository.UPbitRepository;
import com.uj.stxtory.service.DealSettingsService;
import com.uj.stxtory.service.deal.DealNotifyService;
import com.uj.stxtory.service.deal.calculate.CalculateUpbitService;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Transactional
@Service
public class UPbitNotifyService implements DealNotifyService {

  private static final String SETTING_NAME = "upbit";

  private final UPbitRepository uPbitRepository;
  private final DealSettingsService dealSettingsService;
  private final CalculateUpbitService calculateUpbitService;

  public UPbitNotifyService(
      UPbitRepository uPbitRepository,
      DealSettingsService dealSettingsService,
      CalculateUpbitService calculateUpbitService) {
    this.uPbitRepository = uPbitRepository;
    this.dealSettingsService = dealSettingsService;
    this.calculateUpbitService = calculateUpbitService;
  }

  public List<UPbitInfo> getSaved() {
    return callSaved().stream().map(UPbitInfo::fromEntity).toList();
  }

  private List<UPbit> callSaved() { // 목표가와 현재가가 비율 상으로 가장 가까운 순
    return uPbitRepository.findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc().stream()
        .filter(u -> u.getExpectedSellingPrice() != u.getMinimumSellingPrice())
        .sorted(
            Comparator.comparing(UPbit::getRenewalCnt)
                .reversed()
                .thenComparingDouble(
                    u ->
                        (u.getExpectedSellingPrice() - u.getTempPrice())
                            / (u.getExpectedSellingPrice() - u.getMinimumSellingPrice())))
        .toList();
  }

  @Async
  @Override
  public void save() {
    List<UPbit> saved = callSaved();

    DealSettingsInfo settings = dealSettingsService.getByName("upbit");
    DealModel model = new UPbitModel(settings.getHighestPriceReferenceDays());

    List<DealItem> saveItems =
        model.calculateByThreeDaysByPageForSaveByWeb(
            1 + ((double) settings.getExpectedLowPercentage() / 100), settings.isVolumeCheck());

    List<UPbit> save =
        saveItems.stream()
            .filter(item -> saved.stream().noneMatch(s -> s.getCode().equals(item.getCode())))
            .map(
                item ->
                    (UPbit)
                        item.toEntity(
                            1 + ((double) settings.getExpectedHighPercentage() / 100),
                            1 + ((double) settings.getExpectedLowPercentage() / 100)))
            .toList();
    uPbitRepository.saveAll(save);

    List<UPbitInfo> deleteList =
        saved.stream()
            .filter(
                s ->
                    saveItems.stream().noneMatch(item -> item.getCode().equals(s.getCode()))
                        && s.getRenewalCnt() == 0.0)
            .map(UPbitInfo::fromEntity)
            .toList();
    delete(saved, new ArrayList<>(deleteList));
  }

  @Override
  public DealModel update() {
    List<UPbit> saved = callSaved();

    List<DealItem> items = saved.stream().map(UPbitInfo::fromEntity).collect(Collectors.toList());

    DealSettingsInfo settings = dealSettingsService.getByName("upbit");
    DealModel model = new UPbitModel(settings.getHighestPriceReferenceDays());
    if (saved.isEmpty()) return model;
    model.calculateForTodayUpdateByWeb(
        new ArrayList<>(items),
        1 + ((double) settings.getExpectedHighPercentage() / 100),
        1 + ((double) settings.getExpectedLowPercentage() / 100));
    List<DealItem> updateItems = model.getNowItems();
    List<DealItem> deleteItems = model.getDeleteItems();

    update(saved, updateItems);
    delete(saved, deleteItems);

    return model;
  }

  private void update(List<UPbit> saved, List<DealItem> updateItems) {
    saved.forEach(
        uPbit ->
            updateItems.stream()
                .filter(pItem -> pItem.getCode().equals(uPbit.getCode()))
                .findFirst()
                .map(
                    item -> {
                      uPbit.setPricingReferenceDate(item.getPricingReferenceDate());
                      uPbit.setExpectedSellingPrice(item.getExpectedSellingPrice());
                      uPbit.setMinimumSellingPrice(item.getMinimumSellingPrice());
                      uPbit.setRenewalCnt(item.getRenewalCnt());
                      uPbit.setTempPrice(item.getTempPrice());
                      uPbit.setSettingPrice(item.getSettingPrice());
                      uPbit.setUpdatedAt(LocalDateTime.now());
                      return uPbit;
                    }));
  }

  private void delete(List<UPbit> saved, List<DealItem> deleteItems) {
    saved.forEach(
        uPbit ->
            deleteItems.stream()
                .filter(pItem -> pItem.getCode().equals(uPbit.getCode()))
                .findFirst()
                .map(
                    item -> {
                      uPbit.setDeletedAt(LocalDateTime.now());
                      return uPbit;
                    }));
  }

  @Override
  @Async
  public void saveHistory() {
    DealSettingsInfo settings = dealSettingsService.getByName(SETTING_NAME);
    UPbitModel model = new UPbitModel(settings.getHighestPriceReferenceDays());

    // 저장로직
    model.getAll().forEach(info -> calculateUpbitService.savePriceHistoryWithLabel(info, model));
  }
}
