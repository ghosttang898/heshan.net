package net.tonghehui.backend.security;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {"app.cors.allowed-origins=https://test.pages.dev", "spring.jpa.show-sql=false"})
@AutoConfigureMockMvc
class CorsIntegrationTest {
    @Autowired MockMvc mvc;
    @Test void onlyConfiguredOriginCanPreflightBearerRequests() throws Exception {
        mvc.perform(options("/api/admin/posts").header("Origin", "https://test.pages.dev")
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization"))
                .andExpect(status().isOk()).andExpect(header().string("Access-Control-Allow-Origin", "https://test.pages.dev"));
        mvc.perform(options("/api/posts").header("Origin", "https://untrusted.example")
                .header("Access-Control-Request-Method", "GET")).andExpect(status().isForbidden());
    }
}
