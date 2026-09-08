package com.uj.stxtory.domain.dto.upbit;

import com.fasterxml.jackson.databind.JsonNode;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.util.FormatUtil;
import java.util.*;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class UPbitPriceInfo implements DealPrice {
  private Date date;
  private double close;
  private double diff;
  private double open;
  private double high;
  private double low;
  private double volume;

  public static List<DealPrice> getPriceInfoByDay(String market, int days) {

    String url =
        String.format("https://api.upbit.com/v1/candles/days?count=%d&market=%s", days, market);

    JsonNode jsonNode = UPbitInfo.getJsonNodeByUrl(url);

    if (jsonNode == null || jsonNode.get("error") != null) return Collections.emptyList();

    List<DealPrice> prices = new ArrayList<>();

    for (JsonNode node : jsonNode) {
      UPbitPriceInfo price = new UPbitPriceInfo();
      price.setDate(
          FormatUtil.stringToDate(
              node.get("candle_date_time_kst").asText().substring(0, 10).replace("-", ".")));
      price.setClose(FormatUtil.stringToDouble(node.get("trade_price").asText()));
      price.setOpen(FormatUtil.stringToDouble(node.get("opening_price").asText()));
      price.setHigh(FormatUtil.stringToDouble(node.get("high_price").asText()));
      price.setLow(FormatUtil.stringToDouble(node.get("low_price").asText()));
      price.setDiff(FormatUtil.stringToDouble(node.get("change_price").asText()));
      price.setVolume(FormatUtil.stringToDouble(node.get("candle_acc_trade_volume").asText()));
      prices.add(price);
    }

    return prices;
  }

  public static Optional<UPbitPriceInfo> getPriceInfoByToday(String market) {

    String url = String.format("https://api.upbit.com/v1/ticker?markets=%s", market);

    JsonNode jsonNode = UPbitInfo.getJsonNodeByUrl(url);

    if (jsonNode == null || jsonNode.get("error") != null) return Optional.empty();

    return Optional.ofNullable(jsonNode.get(0))
        .map(
            node -> {
              UPbitPriceInfo price = new UPbitPriceInfo();
              price.setDate(new Date());
              price.setClose(FormatUtil.stringToDouble(node.get("trade_price").asText()));
              price.setOpen(FormatUtil.stringToDouble(node.get("opening_price").asText()));
              price.setHigh(FormatUtil.stringToDouble(node.get("high_price").asText()));
              price.setLow(FormatUtil.stringToDouble(node.get("low_price").asText()));
              price.setDiff(FormatUtil.stringToDouble(node.get("change_price").asText()));
              price.setVolume(FormatUtil.stringToDouble(node.get("acc_trade_volume").asText()));
              return price;
            });
  }
}
