package com.uj.stxtory.controller;

import com.uj.stxtory.domain.entity.TbUser;
import com.uj.stxtory.service.UserService;
import com.uj.stxtory.service.account.upbit.UPbitAccountService;
import jakarta.validation.Valid;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.SessionAttributes;
import org.springframework.web.bind.support.SessionStatus;

@Controller
@SessionAttributes("user")
@Slf4j
public class UserController {

  private final UserService userService;
  private final UPbitAccountService uPbitAccountService;

  public UserController(UserService userService, UPbitAccountService uPbitAccountService) {
    this.userService = userService;
    this.uPbitAccountService = uPbitAccountService;
  }

  @ModelAttribute
  public void tbUser(Model model) {
    model.addAttribute("user", new TbUser());
  }

  @GetMapping(value = "/login")
  public String loginPage() {
    return "user/login";
  }

  @GetMapping("/join")
  public String joinForm() {
    return "user/join";
  }

  @PostMapping("/join")
  public String join(
      @Valid @ModelAttribute("user") TbUser user, BindingResult result, SessionStatus status) {
    boolean idDupl = userService.isIdDupl(user.getUserLoginId());
    if (result.hasErrors() || idDupl) {
      if (idDupl)
        result.rejectValue("userLoginId", "duplicate.userForm.userLoginId", "이미 사용 중인 아이디입니다.");
      return "user/join";
    }
    userService.save(user);
    status.setComplete();
    return "user/login";
  }

  @GetMapping("/my")
  public String my(Model model, @AuthenticationPrincipal String userLoginId) {
    settingMyUpbbit(model, userLoginId);
    model.addAttribute(
        "user",
        userService
            .findByLoginId(userLoginId)
            .orElseThrow(() -> new UsernameNotFoundException(userLoginId + " is not found")));

    return "user/my";
  }

  @PostMapping("/my")
  public String update(
      Model model,
      @Valid @ModelAttribute("user") TbUser user,
      BindingResult result,
      SessionStatus status) {
    settingMyUpbbit(model, user.getUserLoginId());
    if (result.hasErrors()) return "user/my";
    userService.updateByLoginId(user);
    status.setComplete();
    return "user/my";
  }

  private void settingMyUpbbit(Model model, String loginId) {
    model.addAttribute("upbitAccounts", uPbitAccountService.getAccount(loginId));
    model.addAttribute("isAuto", uPbitAccountService.isAuto(loginId));
  }
}
