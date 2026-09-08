package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.UPbit;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "sql_upbit")
public interface UPbitRepository extends JpaRepository<UPbit, Long> {
  List<UPbit> findAllByDeletedAtIsNullOrderByPricingReferenceDateDesc();
}
