package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.TbUPbitKey;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

// @RepositoryRestResource(path = "upbit_key")
public interface TbUPbitKeyRepository extends JpaRepository<TbUPbitKey, Long> {
  Optional<TbUPbitKey> findByUserLoginId(String userLoginId);
}
