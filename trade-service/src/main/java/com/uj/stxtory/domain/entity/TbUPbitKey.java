package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Data;
import lombok.ToString;

@Data
@ToString(exclude = {"accessKey", "secretKey"})
@Entity
@Table(name = "tb_upbit_key")
public class TbUPbitKey {
  @Id @GeneratedValue private Long id;

  @Column(name = "user_login_id", nullable = false)
  private String userLoginId;

  @Column(name = "access_key", nullable = false)
  private String accessKey;

  @Column(name = "secret_key", nullable = false)
  private String secretKey;

  @Column(name = "auto_on", nullable = false)
  private Boolean autoOn = true;
}
