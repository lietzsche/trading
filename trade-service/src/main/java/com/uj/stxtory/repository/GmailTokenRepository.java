package com.uj.stxtory.repository;

import com.uj.stxtory.domain.entity.GmailToken;
import org.springframework.data.jpa.repository.JpaRepository;

public interface GmailTokenRepository extends JpaRepository<GmailToken, Long> {}
