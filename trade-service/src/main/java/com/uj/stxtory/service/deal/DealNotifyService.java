package com.uj.stxtory.service.deal;

import com.uj.stxtory.domain.dto.deal.DealModel;

public interface DealNotifyService {
  void save();

  DealModel update();

  void saveHistory();
}
