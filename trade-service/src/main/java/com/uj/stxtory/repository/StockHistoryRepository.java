package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.StockHistory;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StockHistoryRepository extends JpaRepository<StockHistory, Long> {
  List<StockHistory> findByCreatedAtAfter(LocalDateTime fromDate);

  Optional<StockHistory> findByCodeAndNameAndCreatedAt(
      String code, String name, LocalDateTime createdAt);

  List<StockHistory> findByCode(String code);
}
