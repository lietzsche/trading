package com.uj.stxtory.service;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthenticationProviderService implements AuthenticationProvider {
  @Autowired private UserService userService;

  private final BCryptPasswordEncoder bCryptPasswordEncoder;

  public AuthenticationProviderService() {
    bCryptPasswordEncoder = new BCryptPasswordEncoder();
  }

  @Override
  public Authentication authenticate(Authentication authentication) throws AuthenticationException {
    String username = authentication.getName();
    String password = authentication.getCredentials().toString();

    UserDetails user = userService.loadUserByUsername(username);

    if (user == null || password == null) throw new BadCredentialsException("Bad Credentials");

    if (bCryptPasswordEncoder.matches(password, user.getPassword()))
      return new UsernamePasswordAuthenticationToken(
          user.getUsername(), user.getPassword(), user.getAuthorities());

    throw new BadCredentialsException("Bad Credentials");
  }

  @Override
  public boolean supports(Class<?> authentication) {
    return UsernamePasswordAuthenticationToken.class.isAssignableFrom(authentication);
  }
}
