package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.TargetMail;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TargetEailRepository extends JpaRepository<TargetMail, String> {

  List<TargetMail> findAllByDeletedAtIsNull();

  Optional<TargetMail> findByEmail(String email);
}
