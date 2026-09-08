package com.uj.stxtory.domain.dto.upbit;

import java.util.List;
import lombok.Data;

@Data
public class UPbitListResponse {
  private List<UPbitAccount> accounts;
}
