package com.uj.stxtory.service;

import com.uj.stxtory.domain.dto.deal.DealSettingsInfo;
import com.uj.stxtory.repository.DealSettingsRepository;
import com.uj.stxtory.repository.StockRepository;
import com.uj.stxtory.repository.UPbitRepository;
import java.time.LocalDateTime;
import java.util.Optional;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@Transactional(readOnly = true)
public class DealSettingsService {

  private final DealSettingsRepository dealSettingsRepository;

  private final StockRepository stockRepository;
  private final UPbitRepository uPbitRepository;

  public DealSettingsService(
      DealSettingsRepository dealSettingsRepository,
      StockRepository stockRepository,
      UPbitRepository uPbitRepository) {
    this.dealSettingsRepository = dealSettingsRepository;
    this.stockRepository = stockRepository;
    this.uPbitRepository = uPbitRepository;
  }

  public DealSettingsInfo getByName(String name) {
    return dealSettingsRepository
        .findByNameAndDeletedAtIsNull(name)
        .map(DealSettingsInfo::fromEntity)
        .orElseGet(() -> DealSettingsInfo.basic(name));
  }

  @Transactional
  public void update(DealSettingsInfo info) {
    dealSettingsRepository
        .findByNameAndDeletedAtIsNull(info.getName())
        .map(
            entity -> {
              entity.setExpectedHighPercentage(info.getExpectedHighPercentage());
              entity.setExpectedLowPercentage(info.getExpectedLowPercentage());
              entity.setHighestPriceReferenceDays(info.getHighestPriceReferenceDays());
              entity.setVolumeCheck(info.isVolumeCheck());
              entity.setUpdatedAt(LocalDateTime.now());
              return entity;
            })
        .orElseGet(() -> dealSettingsRepository.save(info.toEntity()));
  }

  @Transactional
  public void applyExpectAndMinimumPriceStock() {
    DealSettingsInfo stockSettings = getByName("stock");
    stockRepository
        .findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc()
        .forEach(
            info -> {
              if (info.getRenewalCnt() == 0) {
                info.setOriginExpectedSellingPrice(
                    info.getSettingPrice()
                        * (1 + ((double) stockSettings.getExpectedHighPercentage() / 100)));
                info.setOriginMinimumSellingPrice(
                    info.getSettingPrice()
                        * (1 + ((double) stockSettings.getExpectedLowPercentage() / 100)));
              }
              info.setExpectedSellingPrice(
                  info.getSettingPrice()
                      * (1 + ((double) stockSettings.getExpectedHighPercentage() / 100)));
              info.setMinimumSellingPrice(
                  info.getSettingPrice()
                      * (1 + ((double) stockSettings.getExpectedLowPercentage() / 100)));
            });
  }

  @Transactional
  public void applyExpectAndMinimumPriceUpbit() {
    DealSettingsInfo upbitSettings = getByName("upbit");
    uPbitRepository
        .findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc()
        .forEach(
            info -> {
              if (info.getRenewalCnt() == 0) {
                info.setOriginExpectedSellingPrice(
                    info.getSettingPrice()
                        * (1 + ((double) upbitSettings.getExpectedHighPercentage() / 100)));
                info.setOriginMinimumSellingPrice(
                    info.getSettingPrice()
                        * (1 + ((double) upbitSettings.getExpectedLowPercentage() / 100)));
              }
              info.setExpectedSellingPrice(
                  info.getSettingPrice()
                      * (1 + ((double) upbitSettings.getExpectedHighPercentage() / 100)));
              info.setMinimumSellingPrice(
                  info.getSettingPrice()
                      * (1 + ((double) upbitSettings.getExpectedLowPercentage() / 100)));
            });
  }

  @Transactional
  public void deleteByName(String name) {
    Optional.ofNullable(name)
        .map(
            n -> {
              switch (n) {
                case "stock" ->
                    stockRepository
                        .findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc()
                        .forEach(entity -> entity.setDeletedAt(LocalDateTime.now()));
                case "upbit" ->
                    uPbitRepository
                        .findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc()
                        .forEach(entity -> entity.setDeletedAt(LocalDateTime.now()));
              }
              return n;
            });
  }
}
