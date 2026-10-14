package net.tonghehui.backend.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;
import net.tonghehui.backend.user.UserRepository;
import net.tonghehui.backend.user.Role;

@SpringBootTest(properties = {"spring.datasource.url=jdbc:h2:mem:input_validation;DB_CLOSE_DELAY=-1",
        "spring.jpa.show-sql=false", "app.admin.bootstrap.enabled=false"})
@AutoConfigureMockMvc
class InputValidationIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired UserRepository users;

    private String register() throws Exception {
        String username = "validation-" + UUID.randomUUID();
        String response = mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", username, "displayName", "Test",
                        "password", "local-test-password", "role", "SUPER_ADMIN"))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.role").value("USER"))
                .andReturn().getResponse().getContentAsString();
        assertThat(users.findByUsername(username).orElseThrow().getRole()).isEqualTo(Role.USER);
        return json.readTree(response).get("token").asString();
    }

    @ParameterizedTest
    @ValueSource(strings = {"username", "displayName", "password"})
    void invalidRegistrationIsRejectedBeforeSaving(String field) throws Exception {
        var data = new HashMap<>(Map.of("username", "invalid-" + UUID.randomUUID(),
                "displayName", "Test", "password", "local-test-password"));
        long before = users.count();
        for (String value : new String[] {"   ", "a".repeat(256)}) {
            data.put(field, value);
            mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                    .content(json.writeValueAsString(data))).andExpect(status().isBadRequest());
        }
        assertThat(users.count()).isEqualTo(before);
    }

    @Test void passwordByteBoundaryAndLoginValidation() throws Exception {
        String username = "unicode-" + UUID.randomUUID();
        for (String path : new String[] {"/api/auth/register", "/api/auth/login"}) {
            mvc.perform(post(path).contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(
                    Map.of("username", username, "displayName", "Test", "password", "中".repeat(25)))))
                    .andExpect(status().isBadRequest());
        }
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(
                Map.of("username", username, "displayName", "Test", "password", "中".repeat(24)))))
                .andExpect(status().isOk());
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(
                Map.of("username", username, "password", "中".repeat(24)))))
                .andExpect(status().isOk());
    }

    @ParameterizedTest
    @ValueSource(strings = {"title", "content", "nickname", "location", "yearRange"})
    void oversizedPostFieldsReturn400(String field) throws Exception {
        var data = new HashMap<>(Map.of("title", "Test", "content", "Test", "type", "FIND_PERSON"));
        data.put(field, "a".repeat(field.equals("content") ? 4001 : 256));
        mvc.perform(post("/api/posts").header("Authorization", "Bearer " + register())
                .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(data)))
                .andExpect(status().isBadRequest());
    }

    @Test void requiredPostFieldsAndAnonymousCommentBoundaries() throws Exception {
        String token = register();
        for (String field : new String[] {"title", "content", "type"}) {
            var data = new HashMap<>(Map.of("title", "Test", "content", "Test", "type", "CHAT"));
            data.remove(field);
            mvc.perform(post("/api/posts").header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(data)))
                    .andExpect(status().isBadRequest());
        }
        String response = mvc.perform(post("/api/posts").header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(Map.of(
                        "title", "中".repeat(255), "content", "中".repeat(4000), "type", "FIND_PERSON",
                        "yearRange", "小学时期", "status", "DELETED", "id", 999999))))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        long id = json.readTree(response).get("id").asLong();
        assertThat(id).isNotEqualTo(999999);
        for (String content : new String[] {" ", "a".repeat(2001)}) {
            mvc.perform(post("/api/posts/" + id + "/comments").contentType(MediaType.APPLICATION_JSON)
                    .content(json.writeValueAsString(Map.of("content", content))))
                    .andExpect(status().isBadRequest());
        }
        mvc.perform(post("/api/posts/" + id + "/comments").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("content", "中".repeat(2000)))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.username").isEmpty());
        mvc.perform(get("/api/posts/" + id)).andExpect(status().isOk());
    }
}
