package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

	private AdminLoginClient adminLoginClient;

	public SecurityConfig(AdminLoginClient adminLoginClient) {
		this.adminLoginClient = adminLoginClient;
	}

	@Bean
	SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
		http.csrf(AbstractHttpConfigurer::disable);
		http.authorizeHttpRequests(request -> request
				.requestMatchers("/instances", "/actuator/**", "/login").permitAll()
				.anyRequest().authenticated());
		http.formLogin(form -> form.defaultSuccessUrl("/"));
		return http.build();
	}

	@Bean
	UserDetailsService userDetailsService() {
		return username -> {
			String password = adminLoginClient.adminLogin(username);
			return User.withUsername(username)
					.password(password)
					.build();
		};
	}

	@Bean
	PasswordEncoder passwordEncoder() {
		return new BCryptPasswordEncoder();
	}
}
