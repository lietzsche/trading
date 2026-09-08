package com.uj.stxtory.util;

import java.util.concurrent.CompletableFuture;

public class ApiUtil {
  // spring에 설정된 스레드 풀을 쓸 경우 중지된 상태에서 다시 호출될 수 있으므로 제 3의 스레드로 비동기 호출
  public static void setDelay(int second) {
    CompletableFuture<String> delayFuture =
        CompletableFuture.supplyAsync(
            () -> {
              try {
                Thread.sleep(second * 1000L);
              } catch (Exception e) {
                throw new RuntimeException(e);
              }
              return "delay " + second;
            });
    delayFuture.join();
  }

  public static void runWithException(Runnable runnable) {
    try {
      runnable.run();
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
  }
}
