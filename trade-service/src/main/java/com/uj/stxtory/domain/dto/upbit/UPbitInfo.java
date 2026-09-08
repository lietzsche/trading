package com.uj.stxtory.domain.dto.upbit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.entity.UPbit;
import com.uj.stxtory.util.ApiUtil;
import java.io.IOException;
import java.time.LocalDateTime;
import java.util.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;

@Data
@NoArgsConstructor
@Slf4j
public class UPbitInfo implements DealItem {

  private String market;
  private String koreanName;
  private String englishName;

  private String name; // 종목명
  private String code; // 종목코드

  private List<UPbitPriceInfo> prices; // 가격정보 리스트

  private double originMinimumSellingPrice;
  private double originExpectedSellingPrice;
  private double minimumSellingPrice;
  private double expectedSellingPrice;
  private double tempPrice;
  private double settingPrice;
  private LocalDateTime updatedAt;
  private LocalDateTime pricingReferenceDate;
  private int renewalCnt;

  @Override
  public void setPrices(List<DealPrice> prices) {
    this.prices = prices.stream().map(p -> (UPbitPriceInfo) p).toList();
  }

  @Override
  public void sellingPriceUpdate(Date pricingDate, double highPer, double lowPer) {
    // 하한 매도 가격은 반올림
    this.minimumSellingPrice = this.expectedSellingPrice * lowPer;
    // 기대 매도 가격은 올림
    this.expectedSellingPrice = this.expectedSellingPrice * highPer;
    this.renewalCnt++;
    this.pricingReferenceDate = LocalDateTime.now();
  }

  public UPbitInfo(
      String name,
      String code,
      double originMinimumSellingPrice,
      double originExpectedSellingPrice,
      double minimumSellingPrice,
      double expectedSellingPrice,
      double tempPrice,
      double settingPrice,
      LocalDateTime updatedAt,
      LocalDateTime pricingReferenceDate,
      int renewalCnt) {
    this.name = name;
    this.code = code;
    this.originMinimumSellingPrice = originMinimumSellingPrice;
    this.originExpectedSellingPrice = originExpectedSellingPrice;
    this.minimumSellingPrice = minimumSellingPrice;
    this.expectedSellingPrice = expectedSellingPrice;
    this.updatedAt = updatedAt;
    this.pricingReferenceDate = pricingReferenceDate;
    this.tempPrice = tempPrice;
    this.settingPrice = settingPrice;
    this.renewalCnt = renewalCnt;
  }

  @Override
  public UPbit toEntity(double highPer, double lowPer) {
    double temp = prices.get(0).getClose();
    double setting = prices.get(0).getClose();
    double minimum = setting * lowPer;
    double expected = setting * highPer;
    return new UPbit(code, name, minimum, expected, minimum, expected, temp, setting);
  }

  public static UPbitInfo fromEntity(UPbit uPbit) {
    return new UPbitInfo(
        uPbit.getName(),
        uPbit.getCode(),
        uPbit.getOriginMinimumSellingPrice(),
        uPbit.getOriginExpectedSellingPrice(),
        uPbit.getMinimumSellingPrice(),
        uPbit.getExpectedSellingPrice(),
        uPbit.getTempPrice(),
        uPbit.getSettingPrice(),
        uPbit.getUpdatedAt(),
        uPbit.getPricingReferenceDate(),
        uPbit.getRenewalCnt());
  }

  public static List<DealItem> getAll() {
    String url = "https://api.upbit.com/v1/market/all";

    JsonNode jsonNode = getJsonNodeByUrl(url);

    if (jsonNode == null || jsonNode.get("error") != null) return Collections.emptyList();

    List<DealItem> coins = new ArrayList<>();
    for (JsonNode node : jsonNode) {
      UPbitInfo coin = new UPbitInfo();
      coin.setCode(node.get("market").asText());
      coin.setName(node.get("korean_name").asText());

      coin.setMarket(node.get("market").asText());
      coin.setKoreanName(node.get("korean_name").asText());
      coin.setEnglishName(node.get("english_name").asText());
      coins.add(coin);
    }

    return coins;
  }

  public static JsonNode getJsonNodeByUrl(String url) {
    Document doc;
    JsonNode jsonNode = null;
    try {
      doc = getDocumentByUrl(url);
      String jsonData = doc.select("body").text();
      ObjectMapper mapper = new ObjectMapper();
      jsonNode = mapper.readTree(jsonData);
    } catch (IOException e) {
      log.info(e.getMessage());
    }
    return jsonNode;
  }

  private static Document getDocumentByUrl(String url) throws IOException {
    // 업비트 요청 수 제한으로 시간 제한 [초] 걸기
    ApiUtil.setDelay(3);

    return Jsoup.connect(url).userAgent("Mozilla/5.0").ignoreContentType(true).timeout(10000).get();
  }
}
