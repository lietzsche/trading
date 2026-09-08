package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.UPbitOrderHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "sql_upbit_order_history")
public interface UPbitOrderHistoryRepository extends JpaRepository<UPbitOrderHistory, Long> {}
