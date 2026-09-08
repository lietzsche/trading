package com.uj.stxtory.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

import com.uj.stxtory.config.SecurityConfig;
import com.uj.stxtory.repository.TradeErrorLogRepository;
import com.uj.stxtory.service.AuthenticationProviderService;
import com.uj.stxtory.service.DealSettingsService;
import com.uj.stxtory.service.UserService;
import com.uj.stxtory.service.account.upbit.UPbitAccountService;
import com.uj.stxtory.service.deal.notify.StockNotifyService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = AdminController.class)
@Import(SecurityConfig.class)
class AdminErrorControllerSecurityTest {
  @Autowired private MockMvc mockMvc;

  @MockitoBean private UserService userService;
  @MockitoBean private AuthenticationProviderService authenticationProviderService;
  @MockitoBean private UPbitAccountService upbitAccountService;
  @MockitoBean private DealSettingsService dealSettingsService;
  @MockitoBean private StockNotifyService stockNotifyService;
  @MockitoBean private TradeErrorLogRepository tradeErrorLogRepository;

  @Test
  void anonymousUserIsRedirectedToLogin() throws Exception {
    mockMvc.perform(get("/admin/errors")).andExpect(status().is3xxRedirection());
  }

  @Test
  void regularUserIsForbidden() throws Exception {
    mockMvc
        .perform(get("/admin/errors").with(user("user").roles("USER")))
        .andExpect(status().isForbidden());
  }

  @Test
  void adminCanViewErrors() throws Exception {
    when(tradeErrorLogRepository.search(isNull(), isNull(), any(Pageable.class)))
        .thenReturn(Page.empty());
    when(tradeErrorLogRepository.findDistinctOperations()).thenReturn(List.of());

    mockMvc
        .perform(get("/admin/errors").with(user("admin").roles("ADMIN")))
        .andExpect(status().isOk())
        .andExpect(view().name("admin/errors"));
  }
}
