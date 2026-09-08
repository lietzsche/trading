package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.UpbitHistoryLabel;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UpbitHistoryLabelRepository extends JpaRepository<UpbitHistoryLabel, Long> {
  Optional<UpbitHistoryLabel> findByCodeAndName(String code, String name);
}
