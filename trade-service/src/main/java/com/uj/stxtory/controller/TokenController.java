package com.uj.stxtory.controller;

import com.uj.stxtory.service.token.TokenService;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class TokenController {

  @Autowired TokenService tokenService;

  @ResponseBody
  @PostMapping("/gmail/pw")
  public boolean gmailToken(@RequestBody String pw) {
    return pw.replaceAll("\\W", "").equals("stxtory");
  }

  @ResponseBody
  @PostMapping("/gmail/token")
  public boolean gmailTokenSave(@RequestBody Map<String, String> map) {
    Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
    tokenService.saveGmailToken(
        map.get("token"), authentication.getPrincipal().toString(), map.get("fromEmail"));
    return true;
  }
}
