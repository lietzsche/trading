package com.uj.stxtory.domain.dto.stock;

import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.util.FormatUtil;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.nodes.Document;
import org.jsoup.select.Elements;

@Data
@AllArgsConstructor
@NoArgsConstructor
@Slf4j
public class StockPriceInfo implements DealPrice {
  private Date date;
  private double close;
  private double diff;
  private double open;
  private double high;
  private double low;
  private double volume;

  public static List<DealPrice> getPriceInfoByPage(String code, int from, int to) {
    List<DealPrice> prices = new ArrayList<>();
    for (int page = from; page <= to; page++) {
      prices.addAll(getPriceInfo(code, page));
    }
    return prices;
  }

  public static List<DealPrice> getPriceInfo(String code, int page) { // 종목 및 페이지로 가격 정보 가져오기
    Document doc =
        StockInfo.getDocumentByUrl(
            String.format(
                "https://finance.naver.com/item/sise_day.nhn?code=%s&page=%d", code, page));
    if (doc == null)
      throw new IllegalStateException("주식 가격을 조회하지 못했습니다. code: " + code + ", page: " + page);

    Elements infoList = doc.select("tr");

    List<DealPrice> prices = new ArrayList<>();

    for (int i = 2; i < infoList.size() - 2; i++) {
      if (i >= 7 && i <= 9) {
        continue;
      }
      StockPriceInfo price = new StockPriceInfo();

      Elements info = infoList.get(i).select("td");
      if (info.size() < 7) {
        throw new IllegalStateException(
            "주식 가격 응답 형식이 올바르지 않습니다. code: " + code + ", page: " + page);
      }
      price.setDate(FormatUtil.stringToDate(info.get(0).text()));
      price.setClose(FormatUtil.stringToLong(info.get(1).text()));
      price.setOpen(FormatUtil.stringToLong(info.get(3).text()));
      price.setHigh(FormatUtil.stringToLong(info.get(4).text()));
      price.setLow(FormatUtil.stringToLong(info.get(5).text()));
      price.setVolume(FormatUtil.stringToLong(info.get(6).text()));

      boolean minusDiffFlag =
          info.get(2).text().contains("하한가") || info.get(2).text().contains("하락");
      price.setDiff(
          FormatUtil.stringToLong(
              info.get(2)
                  .text()
                  .replace("상한가", "")
                  .replace("하한가", "")
                  .replace("상승", "")
                  .replace("하락", "")
                  .replace("보합", "")
                  .trim()));
      if (minusDiffFlag) {
        price.setDiff(price.getDiff() * -1);
      }

      prices.add(price);
    }

    return prices;
  }
}
