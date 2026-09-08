package com.uj.stxtory.service;

import com.uj.stxtory.domain.entity.TradeErrorLog;
import com.uj.stxtory.repository.TradeErrorLogRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
public class TradeErrorLogService {
  private final TradeErrorLogRepository repository;

  public TradeErrorLogService(TradeErrorLogRepository repository) {
    this.repository = repository;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void record(String source, String operation, Throwable error) {
    try {
      repository.saveAndFlush(new TradeErrorLog(source, operation, error));
    } catch (Exception saveError) {
      log.error(
          "거래 오류를 DB에 저장하지 못했습니다. source: {}, operation: {}",
          source,
          operation,
          saveError);
    }
  }
}
