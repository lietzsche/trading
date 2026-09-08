package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.StockHistoryLabel;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

// 코드와 이름을 함께 호출해야함, 코드 대응 이름이 바뀌는 경우가 있음
public interface StockHistoryLabelRepository extends JpaRepository<StockHistoryLabel, Long> {
  Optional<StockHistoryLabel> findByCodeAndName(String code, String name);
}
