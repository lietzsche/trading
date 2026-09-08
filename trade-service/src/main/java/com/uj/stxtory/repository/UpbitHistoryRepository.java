package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.UpbitHistory;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UpbitHistoryRepository extends JpaRepository<UpbitHistory, Long> {
  List<UpbitHistory> findByCreatedAtAfter(LocalDateTime fromDate);

  Optional<UpbitHistory> findByCodeAndNameAndCreatedAt(
      String code, String name, LocalDateTime createdAt);

  List<UpbitHistory> findByCode(String code);
}
