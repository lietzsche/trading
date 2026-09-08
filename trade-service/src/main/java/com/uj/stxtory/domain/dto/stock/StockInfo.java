package com.uj.stxtory.domain.dto.stock;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.entity.Stock;
import java.io.IOException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.stream.Collectors;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.Connection;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;

@Data
@Slf4j
@NoArgsConstructor
public class StockInfo implements DealItem {
  private String name; // 종목명
  private String code; // 종목코드
  private int totalPage; // 네이버에서 가져올 전체 페이지
  private List<StockPriceInfo> prices; // 가격정보 리스트
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
    this.prices = prices.stream().map(p -> (StockPriceInfo) p).toList();
  }

  // 하한 및 기대 매도 가격 업데이트
  @Override
  public void sellingPriceUpdate(Date pricingDate, double highPer, double lowPer) {
    // 하한 매도 가격은 반올림
    this.minimumSellingPrice = this.expectedSellingPrice * lowPer;
    // 기대 매도 가격은 올림
    this.expectedSellingPrice = this.expectedSellingPrice * highPer;
    this.renewalCnt++;
    this.pricingReferenceDate = LocalDateTime.now();
  }

  public StockInfo(
      String name,
      String code,
      double originMinimumSellingPrice,
      double originExpectedSellingPrice,
      double minimumSellingPrice,
      double expectedSellingPrice,
      LocalDateTime updatedAt,
      LocalDateTime pricingReferenceDate,
      double tempPrice,
      double settingPrice,
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
  public Stock toEntity(double highPer, double lowPer) {
    double temp = prices.get(0).getClose();
    double setting = prices.get(0).getClose();
    double minimum = setting * lowPer;
    double expected = setting * highPer;
    return new Stock(code, name, minimum, expected, minimum, expected, temp, setting);
  }

  public static StockInfo fromEntity(Stock stock) {
    return new StockInfo(
        stock.getName(),
        stock.getCode(),
        stock.getOriginMinimumSellingPrice(),
        stock.getOriginExpectedSellingPrice(),
        stock.getMinimumSellingPrice(),
        stock.getExpectedSellingPrice(),
        stock.getUpdatedAt(),
        stock.getPricingReferenceDate(),
        stock.getTempPrice(),
        stock.getSettingPrice(),
        stock.getRenewalCnt());
  }

  public static List<DealItem> getCompanyInfo() { // 기본정보 가져오기
    List<StockInfo> stocks = new ArrayList<>();
    Document doc;
    try {
      doc =
          getDocumentByUrl(
              "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13");
    } catch (Exception e) {
      throw new RuntimeException("getCompanyInfo error");
    }

    if (doc == null) return new ArrayList<>();

    Elements infoList = doc.select("tr");
    for (int i = 1; i < infoList.size(); i++) {
      Elements info = infoList.get(i).select("td");
      if (info.size() < 2) continue;
      StockInfo stock = new StockInfo();
      stock.setName(info.get(0).text());
      stock.setCode(info.get(1).text());
      stocks.add(stock);
    }

    return stocks.stream()
        .filter(s -> isIdentifier(s.getCode()))
        .collect(Collectors.toList());
  }

  public static Boolean isIdentifier(String code) {
    Document doc;
    try {
      doc =
          getDocumentByUrl(
              String.format("https://finance.naver.com/item/main.naver?code=%s", code));
    } catch (Exception e) {
      log.info("getStockMarketIdentifier error: " + code);
      return false;
    }

    if (doc == null) return false;

    Elements kospiList = doc.select("img.kospi");

    for (Element img : kospiList) {
      String altText = img.attr("alt");
      if ("코스피".equals(altText)) return true;
    }

    Elements kosdaqList = doc.select("img.kosdaq");
    for (Element img : kosdaqList) {
      String altText = img.attr("alt");
      if ("코스닥".equals(altText)) return true;
    }

    return false;
  }

  //    public static int getPriceTotalPage(String code) throws IOException { // 가격 정보 가져올 때, 전체 페이지
  // 가져오기
  //        Document doc =
  // getDocumentByUrl(String.format("http://finance.naver.com/item/sise_day.nhn?code=%s", code));
  //
  //        Element pgRR = doc.select(".pgRR a").get(0);
  //        String href = pgRR.attr("href");
  //        int totalPage = Integer.valueOf(href.substring(href.indexOf("&page=") + 6).trim());
  //        return totalPage;
  //    }

  public static Document getDocumentByUrl(String url) {
    for (int attempt = 1; attempt <= 3; attempt++) {
      try {
        Connection.Response response =
            Jsoup.connect(url)
                .userAgent("Mozilla/5.0")
                .ignoreHttpErrors(true)
                .ignoreContentType(true)
                .timeout(10000)
                .execute();
        if (response.statusCode() >= 200 && response.statusCode() < 300) {
          return response.parse();
        }
        log.warn(
            "외부 주식 데이터 HTTP 오류. url: {}, status: {}, attempt: {}",
            url,
            response.statusCode(),
            attempt);
      } catch (IOException e) {
        log.warn(
            "외부 주식 데이터 연결 오류. url: {}, attempt: {}, error: {}",
            url,
            attempt,
            e.getClass().getSimpleName());
      }
      if (attempt < 3) {
        try {
          Thread.sleep(500L * attempt);
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          return null;
        }
      }
    }
    return null;
  }
}
