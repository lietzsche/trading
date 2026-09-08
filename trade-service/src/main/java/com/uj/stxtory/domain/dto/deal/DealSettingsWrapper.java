package com.uj.stxtory.domain.dto.deal;

import java.util.List;
import lombok.Data;

@Data
public class DealSettingsWrapper {
  private List<DealSettingsInfo> settings;
}
