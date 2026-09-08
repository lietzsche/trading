package com.uj.stxtory.controller;

import com.uj.stxtory.service.mail.MailService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;

@Controller
public class EmailController {
  @Autowired MailService mailService;

  @ResponseBody
  @PostMapping("/gmail/target")
  public boolean addTarget(@RequestBody String target) {
    mailService.gmailTaretEmailSave(target.replace("\"", ""));
    return true;
  }

  @DeleteMapping("/gmail/target/{email}")
  public ResponseEntity<Boolean> deleteTarget(@PathVariable("email") String email) {
    boolean isDeleted = mailService.gmailTaretEmailDelete(email);
    return ResponseEntity.ok(isDeleted);
  }
}
