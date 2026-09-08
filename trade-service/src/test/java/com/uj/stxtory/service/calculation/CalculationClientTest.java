package com.uj.stxtory.service.calculation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class CalculationClientTest {

  @Test
  void sendsSnakeCaseSelectionContractAndReadsSelectedCodes() {
    RestClient.Builder builder = RestClient.builder().baseUrl("http://calculation-service:8000");
    MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    CalculationClient client = new CalculationClient(builder.build());
    DealItem item = mock(DealItem.class);
    DealPrice price = mock(DealPrice.class);
    when(item.getCode()).thenReturn("KRW-BTC");
    when(item.getName()).thenReturn("비트코인");
    when(price.getClose()).thenReturn(100D);
    when(price.getHigh()).thenReturn(110D);
    when(price.getLow()).thenReturn(90D);
    when(price.getVolume()).thenReturn(10D);
    server
        .expect(requestTo("http://calculation-service:8000/v1/recommendations/select"))
        .andExpect(jsonPath("$.low_percentage").value(-5D))
        .andExpect(jsonPath("$.amplitude_check").value(false))
        .andRespond(withSuccess("{\"selected_codes\":[\"KRW-BTC\"]}", MediaType.APPLICATION_JSON));

    List<String> selected =
        client.select(List.of(item), Map.of("KRW-BTC", List.of(price)), -5, 20, false, false);

    assertThat(selected).containsExactly("KRW-BTC");
    server.verify();
  }

  @Test
  void readsAutoTradeDecision() {
    RestClient.Builder builder = RestClient.builder().baseUrl("http://calculation-service:8000");
    MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    CalculationClient client = new CalculationClient(builder.build());
    server
        .expect(requestTo("http://calculation-service:8000/v1/auto-trade/decide"))
        .andRespond(
            withSuccess(
                "{\"actions\":[{\"side\":\"SELL\",\"market\":\"KRW-ADA\"}]}",
                MediaType.APPLICATION_JSON));

    assertThat(client.decideAutoTrade(List.of("KRW-BTC"), List.of("ADA")))
        .containsExactly(new CalculationClient.TradeAction("SELL", "KRW-ADA"));
    server.verify();
  }
}
