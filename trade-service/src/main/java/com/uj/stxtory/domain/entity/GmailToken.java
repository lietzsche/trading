package com.uj.stxtory.domain.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import lombok.Data;
import lombok.RequiredArgsConstructor;

@Entity
@Data
@RequiredArgsConstructor
public class GmailToken extends Base {
  @Id @GeneratedValue private Long id;

  @Column(name = "gmail_token", nullable = false)
  private String gmailToken;

  @Column(name = "user_login_id", nullable = false)
  private String userLoginId;

  @Column(name = "from_email", nullable = false)
  private String fromEmail;

  public GmailToken(String gmailToken, String userLoginId, String fromEmail) {
    this.gmailToken = gmailToken;
    this.userLoginId = userLoginId;
    this.fromEmail = fromEmail;
  }
}
