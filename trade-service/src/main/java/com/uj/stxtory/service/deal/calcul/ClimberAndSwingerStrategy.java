package com.uj.stxtory.service.deal.calcul;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.dto.deal.DealPrice;
import com.uj.stxtory.domain.dto.stock.StockModel;
import com.uj.stxtory.util.FormatUtil;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;

@Slf4j
public class ClimberAndSwingerStrategy {

  // Climber 조건: 거래량이 급등 없이 점진적 상승 & 가격도 꾸준히 우상향
  static boolean isClimber(List<Double> volumes, List<Double> closes, int startIdx, int endIdx) {
    double startVol = volumes.get(startIdx);
    double endVol = volumes.get(endIdx);
    double startClose = closes.get(startIdx);
    double endClose = closes.get(endIdx);

    // 거래량이 급등 없이 상승
    for (int i = startIdx + 1; i <= endIdx; i++) {
      if (volumes.get(i) > volumes.get(i - 1) * 1.5) return false;
    }
    // 거래량이 전체적으로 증가하고, 가격도 상승
    return endVol >= startVol && endClose > startClose;
  }

  // Swinger 포인트: 최근 며칠간 거래량 급등 + 가격 급락
  static List<String> findSwingerPoints(
      List<Double> volumes,
      List<Double> closes,
      List<DealPrice> days,
      int window,
      double volumeSpike,
      double priceDrop) {
    List<String> swingPoints = new ArrayList<>();
    for (int i = 1; i < closes.size(); i++) {
      // 최근 window일 간에 체크 (예시: 3일)
      if (i < window) continue;
      boolean volSpike = false, priceFell = false;
      for (int j = i - window + 1; j <= i; j++) {
        if (volumes.get(j) > volumes.get(j - 1) * volumeSpike) volSpike = true;
        if (closes.get(j) < closes.get(j - 1) * (1 - priceDrop)) priceFell = true;
      }
      if (volSpike && priceFell) swingPoints.add(FormatUtil.dateToString(days.get(i).getDate()));
    }
    return swingPoints;
  }

  public static void main(String[] args) throws Exception {

    List<DealItem> climberStocks = new ArrayList<>();
    Map<DealItem, List<String>> swingPointsStocks = new HashMap<>();

    StockModel model = new StockModel(130);

    model.getAll().parallelStream()
        .forEach(
            item -> {
              List<DealPrice> prices = model.getPriceByPage(item, 1, 2);

              if (prices.size() < 20 || prices.stream().anyMatch(price -> price.getDate() == null))
                return;

              // 1. 리스트로 변환
              List<Double> closeList = new ArrayList<>();
              List<Double> volumeList = new ArrayList<>();
              for (DealPrice p : prices) {
                closeList.add(p.getClose());
                volumeList.add(p.getVolume());
              }

              // 2. Climber 판별 (마지막 20일 기준)
              int period = 20;
              int startIdx = closeList.size() - period;
              int endIdx = closeList.size() - 1;
              boolean isClimber = isClimber(volumeList, closeList, startIdx, endIdx);

              if (isClimber) {
                climberStocks.add(item);
              }

              // 3. Swinger 포인트 탐지 (최근 3일 중 거래량 2배 이상 & 가격 5%↓)
              List<String> swingPoints =
                  findSwingerPoints(volumeList, closeList, prices, 3, 2.0, 0.05);
              if (!swingPoints.isEmpty()) {
                swingPointsStocks.put(item, swingPoints);
              }
            });

    log.info("Climber & Swinger 전략 결과");
    log.info("[Climber] : 최근 20일간 점진적 거래량 증가 & 꾸준한 가격 상승을 보였습니다.");
    log.info("장기 분할매수 및 우상향 추종 전략 추천 종목");
    climberStocks.forEach(c -> log.info(c.getName()));
    log.info("--------------------------");
    log.info("[Swinger] : 최근 단기 스윙 기회");
    log.info("변동성 트레이딩/반등 노림 전략 참고");
    swingPointsStocks.forEach(
        (item, points) -> {
          log.info(item.getName());
          log.info("포착일 → " + String.join(", ", points) + "\n");
        });
  }
}
