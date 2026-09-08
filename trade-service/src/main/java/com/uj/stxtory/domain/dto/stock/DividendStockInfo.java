package com.uj.stxtory.domain.dto.stock;

import com.uj.stxtory.domain.entity.DividendStock;
import com.uj.stxtory.util.FormatUtil;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;

@Slf4j
@Data
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class DividendStockInfo {
  private String name;
  private Double dividendRate;
  private LocalDate exDivDate;
  private LocalDate payDate;

  public static DividendStockInfo fromEntity(DividendStock entity) {
    return DividendStockInfo.builder()
        .name(entity.getName())
        .dividendRate(entity.getDividendRate())
        .exDivDate(entity.getExDivDate())
        .payDate(entity.getPayDate())
        .build();
  }

  public static List<DividendStock> getDividendStocks() {
    return StockInfo.getCompanyInfo().stream()
        .map(
            info -> {
              List<LocalDate> dates = getDateListAboutDividend(info.getCode());
              return DividendStock.of(
                  info.getCode(),
                  info.getName(),
                  getDividendStock(info.getCode()),
                  dates.size() == 2 ? dates.get(0) : null,
                  dates.size() == 2 ? dates.get(1) : null);
            })
        .filter(Objects::nonNull)
        .filter(ds -> !ds.getDividendRate().equals(0.0))
        .toList();
  }

  // 배당 수익률 가져오기
  public static double getDividendStock(String code) {
    double dividendRate = 0.0;

    String url = String.format("https://finance.naver.com/item/main.naver?code=%s", code);
    Document doc = StockInfo.getDocumentByUrl(url);
    if (doc == null) {
      return dividendRate;
    }

    try {
      // 배당수익률(%) 값을 가져옴
      Elements dividendRateElements = doc.select("em#_dvr");

      for (Element el : dividendRateElements) {
        if (el != null) {
          String text = el.text().replace("%", "").trim(); // "4.56%" → "4.56"
          if (!text.isEmpty() && text.matches(".*\\d.*")) {
            dividendRate = Double.parseDouble(text); // 문자열을 double로 파싱
          }
        }
      }
    } catch (Exception e) {
      log.warn("checkIfDividendStock failed: " + code, e);
      dividendRate = 0.0;
    }
    return dividendRate;
  }

  public static List<LocalDate> getDateListAboutDividend(String code) {

    List<LocalDate> results = new ArrayList<>();

    // 2. 네이버에서 시장 구분 읽기 (코스피/코스닥)
    String naverUrl = String.format("https://finance.naver.com/item/main.naver?code=%s", code);
    Document navDoc = StockInfo.getDocumentByUrl(naverUrl);
    String marketSuffix = "KS"; // 기본값은 코스피
    if (navDoc != null) {
      Element codeElement = navDoc.selectFirst("dl.blind dd:contains(종목코드)");
      if (codeElement != null) {
        String text = codeElement.text();
        // 종목코드 뒤에 "코스닥"이 있으면 KQ로 변경
        if (text.contains("코스닥")) {
          marketSuffix = "KQ";
        }
      }
    }

    // 3. Digrin 페이지에서 배당락/지급일 추출
    String digUrl =
        String.format("https://www.digrin.com/stocks/detail/%s.%s/", code, marketSuffix);
    Document digDoc = StockInfo.getDocumentByUrl(digUrl);
    if (digDoc != null) {
      // 테이블 선택 – Ex-dividend date/Payable date가 포함된 첫 번째 표
      Element table = digDoc.selectFirst("table.table-striped.table-bordered.table-sm");
      if (table != null) {
        Element firstRow = table.selectFirst("tbody tr");
        if (firstRow != null) {
          Elements td = firstRow.select("td");
          if (td.size() >= 2) {
            results.add(FormatUtil.stringToLocalDate(td.get(0).text().trim())); // 배당락일
            results.add(FormatUtil.stringToLocalDate(td.get(1).text().trim())); // 지급일
          }
        }
      }
    }

    return results;
  }
}
