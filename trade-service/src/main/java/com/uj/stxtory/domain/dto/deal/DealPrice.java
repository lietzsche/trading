package com.uj.stxtory.domain.dto.deal;

import java.util.Date;

public interface DealPrice {
  double getVolume();

  double getDiff();

  double getClose();

  double getHigh();

  double getLow();

  double getOpen();

  Date getDate();
}
