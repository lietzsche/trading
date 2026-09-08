package com.uj.stxtory.service.account.upbit;

import com.uj.stxtory.domain.dto.upbit.UPbitAccount;
import com.uj.stxtory.domain.dto.upbit.UPbitOrderResponse;
import com.uj.stxtory.domain.dto.upbit.UpbitOrderChanceResponse;
import java.util.List;
import java.util.Map;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(name = "upbitClient", url = "https://api.upbit.com")
public interface UpbitClient {
  @GetMapping("/v1/accounts")
  List<UPbitAccount> getAccount(@RequestHeader("Authorization") String authorizationToken);

  @PostMapping(value = "/v1/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
  UPbitOrderResponse placeOrder(
      @RequestHeader("Authorization") String authorizationToken,
      @RequestBody Map<String, String> orderRequest);

  @GetMapping("/v1/orders/chance")
  UpbitOrderChanceResponse getOrdersChance(
      @RequestHeader("Authorization") String authorizationToken,
      @RequestParam("market") String market);
}
