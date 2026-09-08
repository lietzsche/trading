package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
    name = "trade_error_log",
    indexes = {
      @Index(name = "idx_trade_error_log_created_at", columnList = "created_at"),
      @Index(name = "idx_trade_error_log_source_operation", columnList = "source,operation")
    })
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class TradeErrorLog {
  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(nullable = false, length = 20)
  private String source;

  @Column(nullable = false, length = 100)
  private String operation;

  @Column(name = "error_type", nullable = false, length = 255)
  private String errorType;

  @Column(nullable = false, length = 2000)
  private String message;

  @Column(name = "created_at", nullable = false)
  private LocalDateTime createdAt;

  public TradeErrorLog(String source, String operation, Throwable error) {
    this.source = limit(source, 20);
    this.operation = limit(operation, 100);
    this.errorType = limit(error.getClass().getName(), 255);
    this.message = limit(error.getMessage() == null ? error.toString() : error.getMessage(), 2000);
    this.createdAt = LocalDateTime.now();
  }

  private static String limit(String value, int maxLength) {
    if (value == null || value.isBlank()) return "UNKNOWN";
    String sanitized =
        value
            .replaceAll("(?i)Bearer\\s+\\S+", "Bearer [REDACTED]")
            .replaceAll(
                "(?i)(access_key|secret_key|password|token)\\s*[=:]\\s*[^\\s,}]+", "$1=[REDACTED]");
    return sanitized.length() <= maxLength ? sanitized : sanitized.substring(0, maxLength);
  }
}
