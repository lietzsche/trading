package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.DividendStock;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DividendStockRepository extends JpaRepository<DividendStock, Long> {
  Optional<DividendStock> findByCodeAndDeletedAtIsNull(String Code);

  List<DividendStock> findAllByDeletedAtIsNullOrderByDividendRateDesc();
}
