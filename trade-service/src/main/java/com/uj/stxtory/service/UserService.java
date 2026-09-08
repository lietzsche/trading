package com.uj.stxtory.service;

import com.uj.stxtory.config.CommonConstant;
import com.uj.stxtory.domain.dto.UserDto;
import com.uj.stxtory.domain.dto.UserListDto;
import com.uj.stxtory.domain.entity.TbUser;
import com.uj.stxtory.repository.UserRepository;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService implements UserDetailsService {

  @Autowired private final UserRepository userRepository;

  public UserService(UserRepository userRepository) {
    this.userRepository = userRepository;
  }

  public boolean isIdDupl(String userLoginId) {
    return userRepository.findByUserLoginId(userLoginId).isPresent();
  }

  public Optional<TbUser> findByLoginId(String loginId) {
    return userRepository.findByUserLoginIdAndDeletedAtIsNull(loginId);
  }

  @Transactional
  public void updateByLoginId(TbUser user) {
    findByLoginId(user.getUserLoginId())
        .map(
            u -> {
              u.setUserPassword(new BCryptPasswordEncoder().encode(user.getUserPassword()));
              u.setUserName(user.getUserName());
              u.setUserPhone(user.getUserPhone());
              u.setUserEmail(user.getUserEmail());
              return u;
            });
  }

  @Transactional
  public void save(TbUser user) {
    BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
    user.setUserPassword(encoder.encode(user.getUserPassword()));
    if (userRepository.findAll().isEmpty()) user.setUserRole(CommonConstant.ROLE_MASTER);
    userRepository.save(user);
  }

  @Override
  public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
    return userRepository
        .findByUserLoginIdAndDeletedAtIsNull(username)
        .map(
            user ->
                User.withUsername(user.getUserLoginId())
                    .password(user.getUserPassword())
                    .roles(user.getUserRole())
                    .build())
        .orElseThrow(() -> new UsernameNotFoundException("User not found: " + username));
  }

  public String getAdmin(String loginId) {
    return userRepository
        .findByUserLoginIdAndDeletedAtIsNull(loginId)
        .filter(
            u ->
                u.getUserRole().equals(CommonConstant.ROLE_ADMIN)
                    || u.getUserRole().equals(CommonConstant.ROLE_MASTER))
        .map(TbUser::getUserPassword)
        .orElseThrow();
  }

  public List<UserDto> getAllForAdmin() {
    return userRepository.findAll().stream()
        .sorted(Comparator.comparing(TbUser::getId))
        .filter(u -> !u.getUserRole().equals(CommonConstant.ROLE_MASTER))
        .map(UserDto::fromEntity)
        .collect(Collectors.toList());
  }

  @Transactional
  public void setRoleAndDel(UserListDto userListDto) {
    userListDto
        .getUsers()
        .forEach(
            u ->
                userRepository
                    .findById(u.getId())
                    .map(
                        uu -> {
                          uu.setUserRole(u.getUserRole());
                          uu.setDeletedAt(u.getIsDel().equals("DEL") ? LocalDateTime.now() : null);
                          return uu;
                        }));
  }
}
