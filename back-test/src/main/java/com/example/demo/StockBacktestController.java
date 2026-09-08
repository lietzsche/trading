package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.client.RestTemplate;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

// http://localhost:8085/stock-backtest?symbols=AAPL,GOOGL,MSFT&interval=1d
@RestController
class StockBacktestController {

    private final RestTemplate restTemplate = new RestTemplate();
    private final DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd");

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

    private List<Candlestick> fetchStockData(String symbol, String interval) throws Exception {
        List<Candlestick> candles = new ArrayList<>();
        ObjectMapper mapper = new ObjectMapper();

        // Example: Fetching data from Yahoo Finance API
        LocalDate endDate = LocalDate.now();
        LocalDate startDate = endDate.minusYears(3);
        String url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?interval=" + interval + "&period1=" + startDate.toEpochDay() * 86400 + "&period2=" + endDate.toEpochDay() * 86400;

        String jsonResponse = restTemplate.getForObject(url, String.class);
        JsonNode root = mapper.readTree(jsonResponse).path("chart").path("result").get(0).path("indicators").path("quote").get(0);

        JsonNode highPrices = root.path("high");
        JsonNode lowPrices = root.path("low");
        JsonNode closePrices = root.path("close");
        JsonNode volumes = root.path("volume");

        for (int i = 0; i < highPrices.size(); i++) {
            candles.add(new Candlestick(
                    highPrices.get(i).asDouble(),
                    lowPrices.get(i).asDouble(),
                    closePrices.get(i).asDouble(),
                    volumes.get(i).asDouble()
            ));
        }

        return candles;
    }

    @GetMapping("/stock-backtest")
    public String backtest(@RequestParam List<String> symbols, @RequestParam(defaultValue = "1d") String interval) throws Exception {
        double startingCapital = 1000000; // Starting capital in USD
        double capital = startingCapital;
        double position = 0; // Position size
        double entryPrice = 0; // Entry price
        boolean canTrade = false; // Indicates if trading is allowed based on stock count

        String selectedStock = null;
        double maxHigh = 0;

        // Step 1: Select stock based on criteria
        List<String> validStocks = new ArrayList<>();

        for (String symbol : symbols) {
            List<Candlestick> candles = fetchStockData(symbol, interval);
            List<Candlestick> last6Months = candles.stream().limit(180).collect(Collectors.toList());

            double stockHigh = last6Months.stream().mapToDouble(c -> c.high).max().orElse(0);
            double todayVolume = candles.get(candles.size() - 1).volume;
            double maxRecentVolume = candles.stream().skip(candles.size() - 3).mapToDouble(c -> c.volume).max().orElse(0);

            if (stockHigh > 0 && todayVolume != maxRecentVolume) {
                validStocks.add(symbol);
            }
        }

        if (validStocks.size() >= 3) {
            canTrade = true;
            selectedStock = validStocks.get(0); // Select the first valid stock
        } else {
            canTrade = false;
        }

        if (!canTrade) {
            return "Not enough valid stocks to trade.";
        }

        // Step 2: Backtest on selected stock
        List<Candlestick> candles = fetchStockData(selectedStock, interval);
        Candlestick selectedCandle = null;

        for (int i = 120; i < candles.size(); i++) {
            int fromIndex = Math.max(0, i - 120);
            int toIndex = i;

            List<Candlestick> last6Months = candles.subList(fromIndex, toIndex);

            double currentHigh = last6Months.stream().mapToDouble(c -> c.high).max().orElse(0);
            int finalI = i;
            List<Candlestick> filteredStocks = last6Months.stream()
                    .filter(c -> c.high == currentHigh)
                    .filter(c -> {
                        int recentVolumeFromIndex = Math.max(0, last6Months.size() - 3);
                        return last6Months.subList(recentVolumeFromIndex, last6Months.size()).stream()
                                .noneMatch(v -> v.volume > candles.get(finalI).volume);
                    })
                    .filter(c -> c.close >= c.high * 0.95)
                    .collect(Collectors.toList());

            if (!filteredStocks.isEmpty()) {
                selectedCandle = filteredStocks.get(0);
            }

            if (selectedCandle != null) {
                double targetHigh = selectedCandle.high;

                if (position == 0 && candles.get(i).close >= targetHigh * 0.95) {
                    position = capital / candles.get(i).close;
                    entryPrice = candles.get(i).close;
                    capital = 0;
                    System.out.println("Bought at: " + entryPrice);
                } else if (position > 0) {
                    // Exit if valid stock count drops below 3
                    if (validStocks.size() < 3 || candles.get(i).close <= entryPrice * 0.95) {
                        capital = position * candles.get(i).close;
                        position = 0;
                        System.out.println("Stopped out at: " + candles.get(i).close + ", Capital: " + capital);
                        selectedCandle = null;
                    } else if (candles.get(i).close >= entryPrice * 1.10) {
                        entryPrice = candles.get(i).close;
                        System.out.println("Trailing stop updated to: " + entryPrice);
                    }
                }
            }
        }

        if (position > 0) {
            capital = position * candles.get(candles.size() - 1).close;
        }

        return "Selected Stock: " + selectedStock + "\nFinal Capital: " + capital + "\nProfit: " + (capital - startingCapital);
    }
}
