package com.uj.stxtory.domain.dto.deal;

import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;

@Getter
@Slf4j
public abstract class DealModel {
  public List<DealItem> deleteItems = new ArrayList<>(); // 업데이트 작업 후 매도 종목
  public List<DealItem> nowItems = new ArrayList<>(); // 갱신 포함 현재 활성화 종목

  public abstract List<DealItem> getAll();

  public int getPage() {
    return 130;
  }

  public abstract List<DealPrice> getPrice(DealItem item, int page);

  public List<DealPrice> getPriceByPage(DealItem item, int from, int to) {
    return getPrice(item, 1);
  }

  public boolean CustomCheckForDelete(DealItem item) {
    return true;
  }

  public boolean useSize() {
    return false;
  }

  public boolean useParallel() {
    return false;
  }

  public List<DealItem> calculateByThreeDaysByPageForSaveByWeb(
      double lowPer, boolean isValueCheck) {
    log.info("\n\n\nsave log start!\n\n\n");

    List<DealItem> allItems = getAll();
    Stream<DealItem> stream =
        useParallel() ? allItems.parallelStream() : allItems.stream();

    return stream
        .filter(
            item -> {
              List<DealPrice> prices = getPrice(item, 1);
              if (prices.size() < 3) return false;

              // 거래량이 0이면 하루 전으로 계산
              int lastdayIndex = prices.get(0).getVolume() == 0 ? 1 : 0;

              // 최근 3일 중 마지막일이 최고 거래량이면 제외
              if (isValueCheck) {
                DealPrice checkPrice =
                    prices.subList(lastdayIndex, (lastdayIndex + 3)).parallelStream()
                        .reduce((p, c) -> p.getVolume() > c.getVolume() ? p : c)
                        .orElse(null);
                if (checkPrice != null && prices.get(0).getVolume() == checkPrice.getVolume())
                  return false;
              }

              // 3일 연달아 가격 상승이 아니면 제외
              if (prices.get(lastdayIndex).getHigh() <= prices.get(lastdayIndex + 1).getHigh()
                  || prices.get(lastdayIndex + 1).getHigh()
                      <= prices.get(lastdayIndex + 2).getHigh()
                  || prices.get(lastdayIndex).getLow() <= prices.get(lastdayIndex + 1).getLow()
                  || prices.get(lastdayIndex + 1).getLow()
                      <= prices.get(lastdayIndex + 2).getLow()) {
                return false;
              }

              // 고점 대비 lowPer 미만이면 제외 - 현재가(종가) 기준
              if (prices.get(lastdayIndex).getClose()
                  < (Math.round(prices.get(lastdayIndex).getHigh() * lowPer))) return false;

              // 조회 기간(6개월) 중 신고가가 아니면 제외
              DealPrice checkPrice =
                  prices.parallelStream()
                      .max(Comparator.comparingDouble(DealPrice::getHigh))
                      .orElse(null);
              if (checkPrice == null || prices.get(lastdayIndex).getHigh() != checkPrice.getHigh())
                return false;

              // 리스트에 저장
              item.setPrices(prices);

              return true;
            })
        // 로그
        .peek(item -> log.info(String.format("\tsuccess:\t%s(%s)", item.getName(), item.getCode())))
        .collect(Collectors.toList());
  }

  public List<DealItem> calculateByThreeDaysByPageForSaveByDatabase(
      double lowPer, double highPer, Map<String, List<DealPrice>> pricesMap, boolean isValueCheck) {
    log.info("\n\n\nsave log start!\n\n\n");

    List<DealItem> allItems = getAll();
    Stream<DealItem> stream =
        useParallel() ? allItems.parallelStream() : allItems.stream();

    return stream
        .filter(
            item -> {
              List<DealPrice> prices = pricesMap.getOrDefault(item.getCode(), new ArrayList<>());
              if (prices.size() < 3) return false;

              // 거래량이 0이면 하루 전으로 계산
              int lastdayIndex = prices.get(0).getVolume() == 0 ? 1 : 0;

              // 최근 3일 중 마지막일이 최고 거래량이면 제외
              if (isValueCheck) {
                DealPrice checkPrice =
                    prices.subList(lastdayIndex, (lastdayIndex + 3)).parallelStream()
                        .reduce((p, c) -> p.getVolume() > c.getVolume() ? p : c)
                        .orElse(null);
                if (checkPrice != null && prices.get(0).getVolume() == checkPrice.getVolume())
                  return false;
              }

              // 마지막일 diff가 5% ~ 15% 내에 있지 않으면 제외
              //              if (useSize()) {
              //                double diffPercent =
              //                    (prices.get(lastdayIndex).getDiff() * 100)
              //                        / prices.get(lastdayIndex + 1).getClose();
              //                if (prices.get(lastdayIndex).getDiff() < 0 || (diffPercent < 5 ||
              // diffPercent > 15))
              //                  return false;
              //              }

              // 3일 연달아 가격 상승이 아니면 제외
              if (prices.get(lastdayIndex).getHigh() <= prices.get(lastdayIndex + 1).getHigh()
                  || prices.get(lastdayIndex + 1).getHigh()
                      <= prices.get(lastdayIndex + 2).getHigh()
                  || prices.get(lastdayIndex).getLow() <= prices.get(lastdayIndex + 1).getLow()
                  || prices.get(lastdayIndex + 1).getLow()
                      <= prices.get(lastdayIndex + 2).getLow()) {
                return false;
              }

              // 고점 대비 lowPer 미만이면 제외 - 현재가(종가) 기준
              if (prices.get(lastdayIndex).getClose()
                  < (Math.round(prices.get(lastdayIndex).getHigh() * (1 + (lowPer / 100)))))
                return false;

              // 조회 기간(6개월) 중 신고가가 아니면 제외
              DealPrice checkPrice =
                  prices.parallelStream()
                      .max(Comparator.comparingDouble(DealPrice::getHigh))
                      .orElse(null);
              if (checkPrice == null || prices.get(lastdayIndex).getHigh() != checkPrice.getHigh())
                return false;

              // 진폭
              // 조회 기간이 20일 이상이면 20일 최대 진폭, 미만이면 조회 기간 최대 진폭 계산
              int size = Math.min(prices.size(), 20);
              double high =
                  prices.subList(0, size).stream().mapToDouble(DealPrice::getHigh).max().orElse(0D);
              double low =
                  prices.subList(0, size).stream().mapToDouble(DealPrice::getHigh).min().orElse(0D);
              if (high == 0D || low == 0D) return false;
              double amplitudePercent = (high - low) / low * 100;
              if (amplitudePercent < (highPer) || amplitudePercent > (highPer * 3)) return false;

              // 리스트에 저장
              item.setPrices(prices);

              return true;
            })
        // 로그
        .peek(item -> log.info(String.format("\tsuccess:\t%s(%s)", item.getName(), item.getCode())))
        .collect(Collectors.toList());
  }

  public void calculateForTodayUpdateByWeb(
      List<DealItem> savedItem, double highPer, double lowPer) {
    savedItem.stream()
        .filter(
            item -> {
              if (!CustomCheckForDelete(item)) {
                deleteItems.add(item);
                return false;
              }
              return true;
            })
        .forEach(
            item -> {
              List<DealPrice> prices = getPrice(item, 1);
              // 거래량이 0이면 하루 전으로 계산
              int lastDayIndex = prices.get(0).getVolume() == 0 ? 1 : 0;
              // 마지막 가격
              DealPrice price = prices.get(lastDayIndex);

              // 당일 현재(종)가가 기대 매도 가격보다 높으면 하한 가격 및 기대 가격 갱신
              while (price.getClose() != 0
                  && item.getExpectedSellingPrice() != 0
                  && price.getClose() >= item.getExpectedSellingPrice()) {
                item.sellingPriceUpdate(new Date(), highPer, lowPer);
                item.setTempPrice(price.getClose());
                item.setSettingPrice(price.getClose()); // 갱신할 때만 설정가
              }
              // 현재 종가(현재가)가 하한 매도 가격 대비 같거나 낮으면 삭제
              if (price.getClose() <= item.getMinimumSellingPrice()) deleteItems.add(item);
              else {
                item.setTempPrice(price.getClose());
                nowItems.add(item);
              }
            });
  }

  public void calculateForTodayUpdateByDatabase(
      List<DealItem> savedItem,
      Map<String, List<DealPrice>> pricesMap,
      double highPer,
      double lowPer) {
    savedItem.stream()
        .filter(
            item -> {
              if (!CustomCheckForDelete(item)) {
                deleteItems.add(item);
                return false;
              }
              return true;
            })
        .forEach(
            item -> {
              // 거래량이 0이면 하루 전으로 계산
              List<DealPrice> prices = pricesMap.get(item.getCode());
              if (prices == null || prices.isEmpty()) {
                log.warn("가격 데이터가 없어 기존 종목 상태를 유지합니다. code: {}", item.getCode());
                nowItems.add(item);
                return;
              }
              int lastDayIndex = prices.get(0).getVolume() == 0 ? 1 : 0;
              if (lastDayIndex >= prices.size()) {
                log.warn("유효한 가격 데이터가 없어 기존 종목 상태를 유지합니다. code: {}", item.getCode());
                nowItems.add(item);
                return;
              }
              // 마지막 가격
              DealPrice price = prices.get(lastDayIndex);

              // 당일 현재(종)가가 기대 매도 가격보다 높으면 하한 가격 및 기대 가격 갱신
              while (price.getClose() != 0
                  && item.getExpectedSellingPrice() != 0
                  && price.getClose() >= item.getExpectedSellingPrice()) {
                item.sellingPriceUpdate(new Date(), highPer, lowPer);
                item.setTempPrice(price.getClose());
                item.setSettingPrice(price.getClose()); // 갱신할 때만 설정가
              }
              // 현재 종가(현재가)가 하한 매도 가격 대비 같거나 낮으면 삭제
              if (price.getClose() <= item.getMinimumSellingPrice()) deleteItems.add(item);
              else {
                item.setTempPrice(price.getClose());
                nowItems.add(item);
              }
            });
  }

  /** 이동평균선, ADX, OBV을 이용한 추세추종 계산 SAMPLE: 최소 계산 일수 70일로 세팅 */
  public List<DealItem> trendFollowingSave() {
    log.info("\n\n\nsave log start!\n\n\n");

    Stream<DealItem> stream = getAll().stream();
    if (useParallel()) stream = getAll().parallelStream();

    return stream
        .filter(
            item -> {
              List<DealPrice> prices = getPriceByPage(item, 1, getPage());
              if (prices.size() < 60) return false; // 최소 60일 데이터 필요 (이동평균 계산)

              int lastdayIndex = prices.get(0).getVolume() == 0 ? 1 : 0;

              // 최근 50일 고점 돌파 여부
              double highestPrice50 =
                  prices.subList(lastdayIndex, lastdayIndex + 50).stream()
                      .mapToDouble(DealPrice::getHigh)
                      .max()
                      .orElse(-1);
              if (prices.get(lastdayIndex).getClose() < highestPrice50) return false;

              // 이동평균선 필터 (5일 > 20일 > 60일)
              double ma5 = calculateMovingAverage(prices, lastdayIndex, 5);
              double ma20 = calculateMovingAverage(prices, lastdayIndex, 20);
              double ma60 = calculateMovingAverage(prices, lastdayIndex, 60);
              if (!(ma5 > ma20 && ma20 > ma60)) return false;

              // ADX 필터 (추세 강한 경우만)
              double adx = calculateADX(prices, lastdayIndex);
              if (adx < 25) return false;

              // OBV 필터 (거래량 증가 확인)
              double obv = calculateOBV(prices);
              if (obv <= 0) return false;

              // 최근 3일 동안 가격 상승
              if (prices.get(lastdayIndex).getHigh() <= prices.get(lastdayIndex + 1).getHigh()
                  || prices.get(lastdayIndex + 1).getHigh()
                      <= prices.get(lastdayIndex + 2).getHigh()
                  || prices.get(lastdayIndex).getLow() <= prices.get(lastdayIndex + 1).getLow()
                  || prices.get(lastdayIndex + 1).getLow()
                      <= prices.get(lastdayIndex + 2).getLow()) {
                return false;
              }

              // 고점 대비 5% 미만이면 제외 (현재가 기준)
              if (prices.get(lastdayIndex).getClose()
                  < (Math.round(prices.get(lastdayIndex).getHigh() * 0.95))) return false;

              // 데이터 저장
              item.setPrices(prices);

              return true;
            })
        .peek(item -> log.info(String.format("\tsuccess:\t%s(%s)", item.getName(), item.getCode())))
        .collect(Collectors.toList());
  }

  /** 이동평균선 계산 */
  private double calculateMovingAverage(List<DealPrice> prices, int lastdayIndex, int period) {
    if (prices.size() < period) return -1;
    return prices.subList(lastdayIndex, lastdayIndex + period).stream()
        .mapToDouble(DealPrice::getClose)
        .average()
        .orElse(-1);
  }

  /** ADX 계산 */
  private double calculateADX(List<DealPrice> prices, int lastdayIndex) {
    if (prices.size() < 14) return -1;
    double adx = 0;
    for (int i = lastdayIndex; i < lastdayIndex + 14; i++) {
      double tr = prices.get(i).getHigh() - prices.get(i).getLow();
      adx += tr;
    }
    return adx / 14;
  }

  /** OBV 계산 */
  private double calculateOBV(List<DealPrice> prices) {
    double obv = 0;
    for (int i = 1; i < prices.size(); i++) {
      if (prices.get(i).getClose() > prices.get(i - 1).getClose()) {
        obv += prices.get(i).getVolume();
      } else {
        obv -= prices.get(i).getVolume();
      }
    }
    return obv;
  }
}
