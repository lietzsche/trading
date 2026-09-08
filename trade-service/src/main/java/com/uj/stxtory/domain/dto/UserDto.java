package com.uj.stxtory.domain.dto;

import com.uj.stxtory.domain.entity.TbUser;
import java.time.LocalDateTime;
import java.util.Optional;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class UserDto {
  private Long id;
  private String userLoginId;
  private String userName;
  private String userRole;
  private String userEmail;
  private String userPhone;
  private String isDel;

  public static UserDto fromEntity(TbUser user) {
    UserDto dto = new UserDto();
    dto.setId(user.getId());
    dto.setUserLoginId(user.getUserLoginId());
    dto.setUserName(user.getUserName());
    dto.setUserEmail(user.getUserEmail());
    dto.setUserPhone(user.getUserPhone());
    dto.setUserRole(user.getUserRole());
    dto.setIsDel(
        Optional.ofNullable(user.getDeletedAt()).map(LocalDateTime::toString).orElse(null));
    return dto;
  }
}
