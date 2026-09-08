package com.uj.stxtory.domain.dto.upbit;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.Data;

@Data
public class UpbitOrderChanceResponse {
  @JsonProperty("bid_fee")
  private String bidFee;

  @JsonProperty("ask_fee")
  private String askFee;

  @JsonProperty("maker_bid_fee")
  private String makerBidFee;

  @JsonProperty("maker_ask_fee")
  private String makerAskFee;

  @JsonProperty("market")
  private Market market;

  @JsonProperty("bid_account")
  private Account bidAccount;

  @JsonProperty("ask_account")
  private Account askAccount;

  @Data
  public static class Market {
    @JsonProperty("id")
    private String id;

    @JsonProperty("name")
    private String name;

    @JsonProperty("order_types")
    private List<String> orderTypes;

    @JsonProperty("order_sides")
    private List<String> orderSides;

    @JsonProperty("bid_types")
    private List<String> bidTypes;

    @JsonProperty("ask_types")
    private List<String> askTypes;

    @JsonProperty("bid")
    private Currency bid;

    @JsonProperty("ask")
    private Currency ask;

    @JsonProperty("max_total")
    private String maxTotal;

    @JsonProperty("state")
    private String state;
  }

  @Data
  public static class Account {
    @JsonProperty("currency")
    private String currency;

    @JsonProperty("balance")
    private String balance;

    @JsonProperty("locked")
    private String locked;

    @JsonProperty("avg_buy_price")
    private String avgBuyPrice;

    @JsonProperty("avg_buy_price_modified")
    private boolean avgBuyPriceModified;

    @JsonProperty("unit_currency")
    private String unitCurrency;
  }

  @Data
  public static class Currency {
    @JsonProperty("currency")
    private String currency;

    @JsonProperty("min_total")
    private String minTotal;
  }
}
