package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import lombok.Data;
import lombok.NoArgsConstructor;

@Entity
@Data
@NoArgsConstructor
public class TargetMail extends Base {

  @Id
  @Column(name = "email", nullable = false, unique = true)
  private String email;

  public TargetMail(String email) {
    this.email = email;
  }
}
