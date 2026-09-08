package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

// http://localhost:8085/upbit-backtest?markets=KRW-BTC,KRW-ETH,KRW-XRP&interval=minutes/5&months=1

@RestController
class UpbitBacktestController {

    private final RestTemplate restTemplate = new RestTemplate();
    private final DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    static class Candlestick {
        double high;
        double low;
        double close;
        double volume;

        public Candlestick(double high, double low, double close, double volume) {
            this.high = high;
            this.low = low;
            this.close = close;
            this.volume = volume;
        }
    }

    private List<Candlestick> fetchUpbitData(String market, String interval, int months) throws Exception {
        List<Candlestick> candles = new ArrayList<>();
        ObjectMapper mapper = new ObjectMapper();

        LocalDateTime endDate = LocalDateTime.now();
        LocalDateTime startDate = endDate.minusMonths(months); // 최근 N개월 데이터 요청

        while (candles.size() < 2000 && endDate.isAfter(startDate)) { // 제한된 데이터 수집
            try {
                String url = "https://api.upbit.com/v1/candles/" + interval + "?market=" + market + "&count=200&to=" + endDate.format(formatter);
                String jsonResponse = restTemplate.getForObject(url, String.class);

                JsonNode root = mapper.readTree(jsonResponse);
                for (JsonNode node : root) {
                    double high = node.get("high_price").asDouble();
                    double low = node.get("low_price").asDouble();
                    double close = node.get("trade_price").asDouble();
                    double volume = node.get("candle_acc_trade_volume").asDouble();
                    candles.add(new Candlestick(high, low, close, volume));
                }

                endDate = endDate.minusMinutes(200 * 5); // 200개의 5분 캔들
                Thread.sleep(200); // 요청 사이에 지연 추가
            } catch (Exception e) {
                System.out.println("Error fetching data for market " + market + ": " + e.getMessage());
                Thread.sleep(1000); // 오류 발생 시 1초 대기 후 재시도
            }
        }

        System.out.println("Fetched " + candles.size() + " candlesticks for market: " + market);
        return candles;
    }

    @GetMapping("/upbit-backtest")
    public String backtest(@RequestParam List<String> markets, @RequestParam(defaultValue = "minutes/5") String interval, @RequestParam(defaultValue = "1") int months) throws Exception {
        double startingCapital = 1000000; // Starting capital in KRW
        double capital = startingCapital;
        double position = 0; // Position size
        double entryPrice = 0; // Entry price

        while (true) {
            // Step 1: Filter markets based on the strategy
            List<String> validMarkets = markets.stream()
                    .filter(market -> {
                        try {
                            List<Candlestick> candles = fetchUpbitData(market, interval, months);
                            List<Candlestick> last6Hours = candles.stream().limit(72).collect(Collectors.toList()); // 6시간 데이터 기준

                            double marketHigh = last6Hours.stream().mapToDouble(c -> c.high).max().orElse(0);
                            double todayVolume = candles.get(0).volume;
                            double maxRecentVolume = candles.stream().limit(3).mapToDouble(c -> c.volume).max().orElse(0);

                            System.out.println("Market: " + market + ", High: " + marketHigh + ", Today Volume: " + todayVolume + ", Max Volume: " + maxRecentVolume);

                            return marketHigh > 0 && todayVolume < maxRecentVolume * 1.2; // 조건 완화
                        } catch (Exception e) {
                            System.out.println("Error filtering market: " + market + ", " + e.getMessage());
                            return false;
                        }
                    })
                    .collect(Collectors.toList());

            System.out.println("Valid markets: " + validMarkets);

            if (validMarkets.size() < 3) {
                // If less than 3 valid markets, stop trading and exit
                if (position > 0) {
                    capital = position * entryPrice;
                    position = 0;
                    System.out.println("Stopped out due to insufficient markets. Capital: " + capital);
                }
                break;
            }

            // Step 2: Select market closest to 10% proximity to its high
            Optional<String> selectedMarket = validMarkets.stream()
                    .sorted((m1, m2) -> {
                        try {
                            List<Candlestick> candles1 = fetchUpbitData(m1, interval, months);
                            List<Candlestick> candles2 = fetchUpbitData(m2, interval, months);
                            double high1 = candles1.get(0).high;
                            double close1 = candles1.get(0).close;
                            double high2 = candles2.get(0).high;
                            double close2 = candles2.get(0).close;
                            return Double.compare(Math.abs(close1 - high1 * 0.90), Math.abs(close2 - high2 * 0.90));
                        } catch (Exception e) {
                            System.out.println("Error comparing markets: " + e.getMessage());
                            return 0;
                        }
                    })
                    .findFirst();

            if (selectedMarket.isEmpty()) {
                System.out.println("No valid market selected.");
                break;
            }

            String marketToTrade = selectedMarket.get();
            System.out.println("Selected market: " + marketToTrade);
            List<Candlestick> candles = fetchUpbitData(marketToTrade, interval, months);
            Candlestick selectedCandle = null;

            for (int i = 72; i < candles.size(); i++) {
                int fromIndex = Math.max(0, i - 72);
                int toIndex = i;

                List<Candlestick> last6Hours = candles.subList(fromIndex, toIndex);
                double currentHigh = last6Hours.stream().mapToDouble(c -> c.high).max().orElse(0);
                int finalI = i;
                List<Candlestick> filteredMarkets = last6Hours.stream()
                        .filter(c -> c.high == currentHigh)
                        .filter(c -> {
                            int recentVolumeFromIndex = Math.max(0, last6Hours.size() - 3);
                            return last6Hours.subList(recentVolumeFromIndex, last6Hours.size()).stream()
                                    .noneMatch(v -> v.volume > candles.get(finalI).volume);
                        })
                        .filter(c -> c.close >= c.high * 0.90) // 매수 조건 완화
                        .collect(Collectors.toList());

                if (!filteredMarkets.isEmpty()) {
                    selectedCandle = filteredMarkets.get(0);
                }

                if (selectedCandle != null) {
                    double targetHigh = selectedCandle.high;

                    if (position == 0 && candles.get(i).close >= targetHigh * 0.90) {
                        position = capital / candles.get(i).close;
                        entryPrice = candles.get(i).close;
                        capital = 0;
                        System.out.println("Bought at: " + entryPrice + ", Close: " + candles.get(i).close);
                    } else if (position > 0) {
                        if (candles.get(i).close <= entryPrice * 0.95) {
                            capital = position * candles.get(i).close;
                            position = 0;
                            System.out.println("Stopped out at: " + candles.get(i).close + ", Capital: " + capital);
                            break;
                        } else if (candles.get(i).close >= entryPrice * 1.10) {
                            entryPrice = candles.get(i).close;
                            System.out.println("Trailing stop updated to: " + entryPrice);
                        }
                    }
                }
            }

            if (position > 0) {
                capital = position * candles.get(candles.size() - 1).close;
                position = 0;
                System.out.println("Final Capital after exiting: " + capital);
            }
        }

        System.out.println("Final Capital: " + capital);
        System.out.println("Profit: " + (capital - startingCapital));
        return "Final Capital: " + capital + "\nProfit: " + (capital - startingCapital);
    }
}
