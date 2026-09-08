package com.uj.stxtory.config;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

@Converter(autoApply = true)
public class LocalDateTimeAttributeConverter implements AttributeConverter<LocalDateTime, String> {

  private static final DateTimeFormatter FORMATTER =
      DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

  @Override
  public String convertToDatabaseColumn(LocalDateTime attribute) {
    return attribute != null ? attribute.format(FORMATTER) : null;
  }

  @Override
  public LocalDateTime convertToEntityAttribute(String dbData) {
    if (dbData == null || dbData.isEmpty()) return null;

    // " " 기준으로 날짜/시간 분리 후 초 단위까지만 자르기
    String trimmed;
    try {
      trimmed = dbData.substring(0, 19); // yyyy-MM-dd HH:mm:ss (정확히 19자리)
    } catch (Exception e) {
      throw new IllegalArgumentException("Invalid datetime format: " + dbData, e);
    }

    return LocalDateTime.parse(trimmed, FORMATTER);
  }
}
