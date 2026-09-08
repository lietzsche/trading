package com.uj.stxtory.domain.entity;

import com.fasterxml.jackson.annotation.JsonFormat;
import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import java.time.LocalDateTime;
import lombok.Data;

@Data
@MappedSuperclass
public abstract class Base {
  @Column(name = "created_at", nullable = false)
  @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "Asia/Seoul")
  private LocalDateTime createdAt = LocalDateTime.now();

  @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "Asia/Seoul")
  @Column(name = "updated_at", nullable = true)
  private LocalDateTime updatedAt;

  @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "Asia/Seoul")
  @Column(name = "deleted_at", nullable = true)
  private LocalDateTime deletedAt;
}
