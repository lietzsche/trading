package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.TradeErrorLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "trade_error_logs", exported = false)
public interface TradeErrorLogRepository extends JpaRepository<TradeErrorLog, Long> {}
