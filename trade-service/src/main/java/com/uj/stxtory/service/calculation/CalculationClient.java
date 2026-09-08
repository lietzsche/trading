package com.uj.stxtory.service.calculation;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CalculationClient {

  private final RestClient restClient;

  @Autowired
  public CalculationClient(
      RestClient.Builder builder, @Value("${calculation-service.url}") String url) {
    SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
    requestFactory.setConnectTimeout(5_000);
    requestFactory.setReadTimeout(30_000);
    this.restClient = builder.baseUrl(url).requestFactory(requestFactory).build();
  }

  CalculationClient(RestClient restClient) {
    this.restClient = restClient;
  }

  public boolean isHealthy() {
    try {
      HealthResponse response =
          restClient.get().uri("/health").retrieve().body(HealthResponse.class);
      return response != null && "UP".equals(response.status());
    } catch (RuntimeException exception) {
      return false;
    }
  }

  public List<String> select(
      List<? extends DealItem> items,
      Map<String, List<DealPrice>> prices,
      double lowPercentage,
      double highPercentage,
      boolean volumeCheck,
      boolean amplitudeCheck) {
    List<Instrument> instruments =
        items.stream()
            .map(item -> new Instrument(item.getCode(), item.getName(), prices(item, prices)))
            .toList();
    SelectionResponse response =
        restClient
            .post()
            .uri("/v1/recommendations/select")
            .contentType(MediaType.APPLICATION_JSON)
            .body(
                new SelectionRequest(
                    instruments, lowPercentage, highPercentage, volumeCheck, amplitudeCheck))
            .retrieve()
            .body(SelectionResponse.class);
    if (response == null) throw new IllegalStateException("계산 서비스의 추천 응답이 비어 있습니다.");
    return response.selectedCodes();
  }

  public List<PositionResult> update(
      List<? extends DealItem> items,
      Map<String, List<DealPrice>> prices,
      double highMultiplier,
      double lowMultiplier) {
    List<Position> positions =
        items.stream()
            .map(
                item ->
                    new Position(
                        item.getCode(),
                        item.getName(),
                        prices(item, prices),
                        item.getExpectedSellingPrice(),
                        item.getMinimumSellingPrice(),
                        item.getTempPrice(),
                        item.getSettingPrice(),
                        item.getRenewalCnt()))
            .toList();
    UpdateResponse response =
        restClient
            .post()
            .uri("/v1/recommendations/update")
            .contentType(MediaType.APPLICATION_JSON)
            .body(new UpdateRequest(positions, highMultiplier, lowMultiplier))
            .retrieve()
            .body(UpdateResponse.class);
    if (response == null) throw new IllegalStateException("계산 서비스의 갱신 응답이 비어 있습니다.");
    return response.positions();
  }

  public List<TradeAction> decideAutoTrade(
      List<String> recommendedMarkets, List<String> currencies) {
    AutoTradeResponse response =
        restClient
            .post()
            .uri("/v1/auto-trade/decide")
            .contentType(MediaType.APPLICATION_JSON)
            .body(
                new AutoTradeRequest(
                    recommendedMarkets, currencies.stream().map(AccountBalance::new).toList(), 3))
            .retrieve()
            .body(AutoTradeResponse.class);
    if (response == null) throw new IllegalStateException("계산 서비스의 자동매매 응답이 비어 있습니다.");
    return response.actions();
  }

  private List<Price> prices(DealItem item, Map<String, List<DealPrice>> prices) {
    return prices.getOrDefault(item.getCode(), List.of()).stream().map(Price::from).toList();
  }

  public record HealthResponse(String status) {}

  public record Price(
      double close, double high, double low, double open, double diff, double volume) {
    static Price from(DealPrice price) {
      return new Price(
          price.getClose(),
          price.getHigh(),
          price.getLow(),
          price.getOpen(),
          price.getDiff(),
          price.getVolume());
    }
  }

  public record Instrument(String code, String name, List<Price> prices) {}

  public record SelectionRequest(
      List<Instrument> instruments,
      @JsonProperty("low_percentage") double lowPercentage,
      @JsonProperty("high_percentage") double highPercentage,
      @JsonProperty("volume_check") boolean volumeCheck,
      @JsonProperty("amplitude_check") boolean amplitudeCheck) {}

  public record SelectionResponse(@JsonProperty("selected_codes") List<String> selectedCodes) {}

  public record Position(
      String code,
      String name,
      List<Price> prices,
      @JsonProperty("expected_selling_price") double expectedSellingPrice,
      @JsonProperty("minimum_selling_price") double minimumSellingPrice,
      @JsonProperty("temp_price") double tempPrice,
      @JsonProperty("setting_price") double settingPrice,
      @JsonProperty("renewal_count") int renewalCount) {}

  public record UpdateRequest(
      List<Position> positions,
      @JsonProperty("high_multiplier") double highMultiplier,
      @JsonProperty("low_multiplier") double lowMultiplier) {}

  public record UpdateResponse(List<PositionResult> positions) {}

  public record PositionResult(
      String code,
      String action,
      @JsonProperty("expected_selling_price") double expectedSellingPrice,
      @JsonProperty("minimum_selling_price") double minimumSellingPrice,
      @JsonProperty("temp_price") double tempPrice,
      @JsonProperty("setting_price") double settingPrice,
      @JsonProperty("renewal_count") int renewalCount,
      @JsonProperty("pricing_reference_date") LocalDateTime pricingReferenceDate) {}

  public record AccountBalance(String currency) {}

  public record AutoTradeRequest(
      @JsonProperty("recommended_markets") List<String> recommendedMarkets,
      List<AccountBalance> balances,
      @JsonProperty("minimum_recommendations") int minimumRecommendations) {}

  public record TradeAction(String side, String market) {}

  public record AutoTradeResponse(List<TradeAction> actions) {}
}
