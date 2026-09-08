package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.Stock;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "sql_stock")
public interface StockRepository extends JpaRepository<Stock, Long> {
  List<Stock> findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc();
}
