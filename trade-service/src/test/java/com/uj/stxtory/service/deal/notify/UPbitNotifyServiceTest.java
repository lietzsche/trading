package com.uj.stxtory.service.deal.notify;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.uj.stxtory.domain.entity.UPbit;
import com.uj.stxtory.repository.UPbitRepository;
import com.uj.stxtory.service.DealSettingsService;
import com.uj.stxtory.service.TradeErrorLogService;
import com.uj.stxtory.service.deal.calculate.CalculateUpbitService;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class UPbitNotifyServiceTest {

  @Test
  void getSavedReturnsOnlyOneRecommendationPerCode() {
    UPbitRepository repository = mock(UPbitRepository.class);
    UPbitNotifyService service =
        new UPbitNotifyService(
            repository,
            mock(DealSettingsService.class),
            mock(CalculateUpbitService.class),
            mock(TradeErrorLogService.class));

    UPbit first = recommendation(1L, "KRW-PIEVERSE", "파이버스");
    UPbit duplicate = recommendation(2L, "KRW-PIEVERSE", "파이버스");
    UPbit other = recommendation(3L, "KRW-BTC", "비트코인");
    when(repository.findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc())
        .thenReturn(List.of(duplicate, first, other));

    assertThat(service.getSaved())
        .extracting("code")
        .containsExactlyInAnyOrder("KRW-PIEVERSE", "KRW-BTC");
  }

  @Test
  void cleanupSoftDeletesNewerActiveDuplicates() {
    UPbitRepository repository = mock(UPbitRepository.class);
    UPbitNotifyService service =
        new UPbitNotifyService(
            repository,
            mock(DealSettingsService.class),
            mock(CalculateUpbitService.class),
            mock(TradeErrorLogService.class));
    UPbit survivor = recommendation(1L, "KRW-PIEVERSE", "파이버스");
    UPbit duplicate = recommendation(2L, "KRW-PIEVERSE", "파이버스");
    when(repository.findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc())
        .thenReturn(List.of(duplicate, survivor));

    service.cleanupDuplicateRecommendations();

    assertThat(survivor.getDeletedAt()).isNull();
    assertThat(duplicate.getDeletedAt()).isNotNull();
    verify(repository).saveAll(List.of(duplicate));
  }

  private UPbit recommendation(Long id, String code, String name) {
    UPbit item = new UPbit();
    item.setId(id);
    item.setCode(code);
    item.setName(name);
    item.setExpectedSellingPrice(120);
    item.setMinimumSellingPrice(80);
    item.setTempPrice(100);
    item.setSettingPrice(100);
    item.setPricingReferenceDate(LocalDateTime.now());
    return item;
  }
}
