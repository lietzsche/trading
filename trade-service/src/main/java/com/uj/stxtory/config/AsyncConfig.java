package com.uj.stxtory.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableAsync
public class AsyncConfig {
  @Bean(name = {"taskExecutor", "poolTaskExecutor"})
  @Primary
  ThreadPoolTaskExecutor poolTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(5);
    executor.setMaxPoolSize(100);
    executor.setQueueCapacity(500);
    executor.setThreadNamePrefix("stock&coin-");
    executor.initialize();
    return executor;
  }

  @Bean
  TaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(30);
    scheduler.setThreadNamePrefix("task-");
    scheduler.initialize();
    return scheduler;
  }
}
