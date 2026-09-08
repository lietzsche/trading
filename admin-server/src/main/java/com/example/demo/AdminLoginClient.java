package com.example.demo;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@FeignClient("trade-service")
public interface AdminLoginClient {
    @PostMapping("/actuator/adminLogin")
    String adminLogin(@RequestBody String credentials);
}
