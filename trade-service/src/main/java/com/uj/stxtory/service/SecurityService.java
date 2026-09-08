package com.uj.stxtory.service;

import com.uj.stxtory.domain.entity.TbUser;
import com.uj.stxtory.repository.UserRepository;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Transactional
@Service
public class SecurityService implements UserDetailsService {

  @Autowired UserRepository userRepository;

  @Override
  @Transactional(readOnly = true)
  public UserDetails loadUserByUsername(String userLoginId) throws UsernameNotFoundException {

    Set<GrantedAuthority> grantedAuthorities = new HashSet<>();

    Optional<TbUser> tbUser = userRepository.findByUserLoginIdAndDeletedAtIsNull(userLoginId);
    if (tbUser.isPresent()) {
      TbUser user = tbUser.get();
      grantedAuthorities.add(new SimpleGrantedAuthority(user.getUserRole()));
      return User.builder()
          .username(user.getUserLoginId())
          .password(user.getUserPassword())
          .authorities(grantedAuthorities)
          .build();
    } else {
      throw new UsernameNotFoundException("can not found User : " + userLoginId);
    }
  }
}
