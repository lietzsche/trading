package com.uj.stxtory.config;

import com.uj.stxtory.service.AuthenticationProviderService;
import com.uj.stxtory.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.builders.AuthenticationManagerBuilder;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.annotation.web.configurers.HeadersConfigurer;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class SecurityConfig implements WebMvcConfigurer {
  @Autowired private UserService userService;
  @Autowired private AuthenticationProviderService authenticationProviderService;

  @Bean
  public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {

    http.csrf(AbstractHttpConfigurer::disable);

    http.formLogin(form -> form.permitAll().loginPage("/login").defaultSuccessUrl("/", true));
    http.authorizeHttpRequests(
        request ->
            request
                .requestMatchers("/join")
                .permitAll()
                .requestMatchers("/admin/**")
                .hasAnyRole(new String[] {CommonConstant.ROLE_ADMIN, CommonConstant.ROLE_MASTER})
                .requestMatchers(
                    "/h2/**", "/sql_stock/**", "/sql_upbit/**", "/sql_upbit_order_history/**")
                .hasRole(CommonConstant.ROLE_MASTER)
                .requestMatchers("/actuator/**", "/collect/**")
                .permitAll()
                .anyRequest()
                .authenticated());
    http.headers(headers -> headers.frameOptions(HeadersConfigurer.FrameOptionsConfig::sameOrigin));

    return http.build();
  }

  @Bean
  AuthenticationManager authenticationManager(HttpSecurity http) throws Exception {
    return http.getSharedObject(AuthenticationManagerBuilder.class)
        .authenticationProvider(authenticationProviderService)
        .userDetailsService(userService)
        .passwordEncoder(new BCryptPasswordEncoder())
        .and()
        .build();
  }
}
