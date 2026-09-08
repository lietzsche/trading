package com.uj.stxtory.util;

import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import lombok.extern.slf4j.Slf4j;

@Slf4j
public class FormatUtil {

  public static Date stringToDate(String str) {
    Date date = null;
    try {
      SimpleDateFormat sdf = new SimpleDateFormat("yyyy.MM.dd");
      date = str.isEmpty() ? null : sdf.parse(str);
    } catch (Exception e) {
      log.info(String.format("stringToDate : str >>>> %s", str));
    }
    return date;
  }

  public static long stringToLong(String str) {
    long result = 0L;
    str = str.isEmpty() ? "0" : str;
    try {
      str = str.replace(",", "");
      result = Long.parseLong(str);
    } catch (Exception e) {
      log.info(String.format("stringToLong : str >>>> %s", str));
    }
    return result;
  }

  public static double stringToDouble(String str) {
    double result = 0;
    if ("null".equals(str) || str == null) return result;
    str = str.isEmpty() ? "0" : str;
    try {
      str = str.replace(",", "");
      result = Double.parseDouble(str);
    } catch (Exception e) {
      log.info(String.format("StringToDouble : str >>>> %s", str));
    }
    return result;
  }

  public static String dateToString(LocalDateTime date) {
    String str = null;
    try {
      DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
      str = date == null ? null : date.format(formatter);
    } catch (Exception e) {
      log.info(String.format("dateToString : date >>>> %s", date));
    }
    return str;
  }

  public static String shortDateToString(LocalDateTime date) {
    String str = null;
    try {
      DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yy-MM-dd HH:mm:ss");
      str = date == null ? null : date.format(formatter);
    } catch (Exception e) {
      log.info(String.format("dateToString : date >>>> %s", date));
    }
    return str;
  }

  public static LocalDateTime dateToLocalDateTime(Date date) {
    // Date -> LocalDateTime
    LocalDateTime localDateTime = null;
    try {

      localDateTime = date.toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime();
    } catch (Exception e) {
      log.warn("dateToLocalDateTime : date >>>> {}", date, e);
    }
    return localDateTime;
  }

  public static LocalDate stringToLocalDate(String str) {
    // String -> LocalDate
    LocalDate localDate = null;
    if (str.isEmpty()) return null;
    try {
      localDate = LocalDate.parse(str);
    } catch (Exception e) {
      log.warn("stringToLocalDate : str >>>> {}", str, e);
    }
    return localDate;
  }

  public static String dateToString(Date date) {
    if (date == null) return null;
    DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    try {
      return date.toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime().format(formatter);
    } catch (Exception e) {
      log.warn("dateToString : date >>>> {}", date, e);
      return null;
    }
  }
}
