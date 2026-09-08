package com.uj.stxtory.service.mail;

import com.uj.stxtory.domain.dto.deal.DealItem;
import com.uj.stxtory.domain.entity.GmailToken;
import com.uj.stxtory.domain.entity.TargetMail;
import com.uj.stxtory.repository.TargetEailRepository;
import com.uj.stxtory.service.token.TokenService;
import com.uj.stxtory.util.FormatUtil;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Transactional
@Service
@Slf4j
public class MailService {

  @Autowired private TokenService tokenService;
  @Autowired private TargetEailRepository targetEailRepository;
  @Autowired private TemplateEngine templateEngine;

  private final Map<String, String> titleDescriptions =
      Map.of("select", " - 선택 종목", "delete", " - 매도 종목");
  private final String SELECT = "select";
  private final String DELETE = "delete";

  public void gmailTaretEmailSave(String target) {
    targetEailRepository.save(new TargetMail(target));
  }

  public List<TargetMail> getTargets() {
    return targetEailRepository.findAllByDeletedAtIsNull();
  }

  public boolean gmailTaretEmailDelete(String target) {
    TargetMail email = targetEailRepository.findByEmail(target).orElse(null);

    if (email == null) return false;

    email.setDeletedAt(LocalDateTime.now());
    return true;
  }

  @Async
  public void noticeSelect(List<DealItem> select, String title) {
    notice(select, title + titleDescriptions.get(SELECT));
  }

  @Async
  public void noticeDelete(List<DealItem> deleted, String title) {
    if (deleted.isEmpty()) return;
    notice(deleted, title + titleDescriptions.get(DELETE));
  }

  private void notice(List<DealItem> all, String title) {
    try {
      Context context = new Context();
      context.setVariable("items", all);
      context.setVariable("subject", title);

      String htmlContent = templateEngine.process("gmail", context);

      sendGmailWithHtml(
          title + ": " + FormatUtil.shortDateToString(LocalDateTime.now()), htmlContent);
    } catch (Exception e) {
      log.info("notice error \n1) title: " + title + "\n2) error: " + e.getMessage());
    }
  }

  public void sendGmailWithHtml(String title, String htmlContent) throws MessagingException {
    GmailToken gmailToken = tokenService.getGmailToken();
    // 등록된 토큰 없으면 메일 발송 정지
    if (gmailToken == null) return;

    String from = gmailToken.getFromEmail();
    String password = gmailToken.getGmailToken();
    List<TargetMail> targets = getTargets();
    for (TargetMail to : targets) {
      // 메일 서버 설정
      JavaMailSenderImpl mailSender = new JavaMailSenderImpl();
      mailSender.setHost("smtp.gmail.com");
      mailSender.setPort(Integer.parseInt("587"));
      mailSender.setUsername(from);
      mailSender.setPassword(password);

      Properties props = mailSender.getJavaMailProperties();
      props.put("mail.smtp.auth", "true");
      props.put("mail.smtp.starttls.enable", "true");

      // MimeMessage 생성
      MimeMessage message = mailSender.createMimeMessage();

      // MimeMessageHelper 사용하여 이메일 설정
      MimeMessageHelper helper =
          new MimeMessageHelper(message, true, "UTF-8"); // true: HTML 형식으로 전송
      helper.setFrom(from);
      helper.setTo(to.getEmail());
      helper.setSubject(title);
      helper.setText(htmlContent, true); // HTML 콘텐츠로 설정

      // 메일 전송
      mailSender.send(message);
    }
  }
}
