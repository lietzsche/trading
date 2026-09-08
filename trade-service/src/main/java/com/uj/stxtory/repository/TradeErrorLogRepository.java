package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.TradeErrorLog;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "trade_error_logs", exported = false)
public interface TradeErrorLogRepository extends JpaRepository<TradeErrorLog, Long> {
  @Query(
      """
      select e from TradeErrorLog e
      where (:source = '' or e.source = :source)
        and (:keyword = ''
          or lower(e.operation) like lower(concat('%', :keyword, '%'))
          or lower(e.errorType) like lower(concat('%', :keyword, '%'))
          or lower(e.message) like lower(concat('%', :keyword, '%')))
      """)
  Page<TradeErrorLog> search(String source, String keyword, Pageable pageable);

  @Query("select distinct e.operation from TradeErrorLog e order by e.operation")
  List<String> findDistinctOperations();
}
