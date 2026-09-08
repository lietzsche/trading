package com.uj.stxtory.domain.entity;

import com.uj.stxtory.config.CommonConstant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Entity
@Data
public class TbUser extends Base {
  @Id @GeneratedValue private Long id;

  @Column(name = "user_login_id", nullable = false)
  @NotBlank(message = "로그인 아이디는 비워둘 수 없습니다.")
  @Size(min = 4, max = 50, message = "로그인 아이디는 4자 이상, 50자 이하여야 합니다.")
  private String userLoginId;

  @Column(name = "user_password", nullable = false)
  @NotBlank(message = "비밀번호는 비워둘 수 없습니다.")
  @Size(min = 8, message = "비밀번호는 최소 8자 이상이어야 합니다.")
  private String userPassword;

  @Column(name = "user_name", nullable = false)
  @NotBlank(message = "사용자 이름은 비워둘 수 없습니다.")
  @Size(max = 100, message = "사용자 이름은 최대 100자 이하여야 합니다.")
  private String userName;

  @Column(name = "user_role", nullable = false)
  private String userRole = CommonConstant.ROLE_USER;

  @Column(name = "user_email", nullable = true)
  @Email(message = "유효한 이메일 주소를 입력해야 합니다.")
  private String userEmail;

  @Column(name = "user_phone", nullable = true)
  @Pattern(
      regexp = "^\\+?[0-9. ()-]{7,25}$",
      message = "전화번호는 7자리 이상 25자리 이하의 숫자 및 허용된 문자만 포함해야 합니다.")
  private String userPhone;
}
