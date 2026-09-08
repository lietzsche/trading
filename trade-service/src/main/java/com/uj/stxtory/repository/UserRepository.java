package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.TbUser;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<TbUser, Long> {
  Optional<TbUser> findByUserLoginIdAndDeletedAtIsNull(String userLoginId);

  Optional<TbUser> findByUserLoginId(String userLoginId);
}
