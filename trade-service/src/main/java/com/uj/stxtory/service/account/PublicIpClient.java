package com.uj.stxtory.service.account;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "publicIpClient", url = "https://api.ipify.org")
public interface PublicIpClient {
  @GetMapping("?format=text")
  String getPublicIp();
}
