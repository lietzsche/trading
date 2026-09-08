package com.uj.stxtory.domain.dto.key;

import com.uj.stxtory.domain.entity.TbUPbitKey;
import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class UPbitKey {
  private String access;
  private String secret;

  public TbUPbitKey toEntity(String userLoginId) {
    TbUPbitKey entity = new TbUPbitKey();
    entity.setAccessKey(this.access);
    entity.setSecretKey(this.secret);
    entity.setAutoOn(false);
    entity.setUserLoginId(userLoginId);
    return entity;
  }

  public static UPbitKey fromEntity(TbUPbitKey entity) {
    return new UPbitKey(entity.getAccessKey(), entity.getSecretKey());
  }
}
