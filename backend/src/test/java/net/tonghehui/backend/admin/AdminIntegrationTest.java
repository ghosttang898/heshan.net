package net.tonghehui.backend.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.time.LocalDateTime;
import java.util.Map;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import net.tonghehui.backend.user.*;
import net.tonghehui.backend.post.*;
import net.tonghehui.backend.comment.*;
import net.tonghehui.backend.moderation.ContentStatus;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:admin_tests;DB_CLOSE_DELAY=-1",
        "spring.jpa.show-sql=false", "app.admin.bootstrap.enabled=false"
})
@AutoConfigureMockMvc
class AdminIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired UserRepository users;
    @Autowired PostRepository posts;
    @Autowired CommentRepository comments;
    @Autowired PasswordEncoder passwords;
    private String adminToken;
    private String userToken;
    private User ordinary;

    @BeforeEach
    void setup() throws Exception {
        comments.deleteAll(); posts.deleteAll(); users.deleteAll();
        User admin = user("admin-test", "Admin", Role.ADMIN);
        ordinary = user("member-test", "Heshan member", Role.USER);
        adminToken = login(admin.getUsername());
        userToken = login(ordinary.getUsername());
    }

    private User user(String username, String displayName, Role role) {
        User user = new User(); user.setUsername(username); user.setDisplayName(displayName);
        user.setPassword(passwords.encode("Test-password-123")); user.setRole(role);
        return users.save(user);
    }

    private String login(String username) throws Exception {
        return body(mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", username, "password", "Test-password-123"))))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).get("token").asText();
    }

    private JsonNode body(String response) throws Exception { return json.readTree(response); }

    private JsonNode createPost(String type, String title) throws Exception {
        return body(mvc.perform(post("/api/posts").header("Authorization", "Bearer " + userToken)
                .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(Map.of(
                        "title", title, "content", "Heshan community content", "type", type,
                        "status", "DELETED", "createdAt", "2000-01-01T00:00:00", "authorUsername", "admin-test"))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("PUBLISHED"))
                .andExpect(jsonPath("$.authorUsername").value("member-test"))
                .andReturn().getResponse().getContentAsString());
    }

    private long createComment(long id, boolean authenticated, String content) throws Exception {
        var request = post("/api/posts/" + id + "/comments").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("content", content, "status", "DELETED")));
        if (authenticated) request.header("Authorization", "Bearer " + userToken);
        return body(mvc.perform(request).andExpect(status().isOk()).andReturn()
                .getResponse().getContentAsString()).get("id").asLong();
    }

    private void change(String resource, long id, String status) throws Exception {
        mvc.perform(patch("/api/admin/" + resource + "/" + id + "/status")
                .header("Authorization", "Bearer " + adminToken).contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("status", status))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value(status));
    }

    @Test
    void adminEndpointsRequireRealAdminIncludingWritesAndUnknownPaths() throws Exception {
        for (String path : new String[]{"dashboard", "posts", "comments", "users", "posts/1", "anything"}) {
            mvc.perform(get("/api/admin/" + path)).andExpect(status().isUnauthorized());
            mvc.perform(get("/api/admin/" + path).header("Authorization", "Bearer " + userToken))
                    .andExpect(status().isForbidden());
        }
        mvc.perform(get("/api/admin/dashboard").header("Authorization", "Bearer invalid.token"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/admin/dashboard").header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk());
        mvc.perform(patch("/api/admin/posts/1/status").header("Authorization", "Bearer " + userToken)
                .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"PUBLISHED\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/posts").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void registrationCannotGrantAdminAndMeNeverLeaksPassword() throws Exception {
        JsonNode result = body(mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"new-member\",\"displayName\":\"New\",\"password\":\"test123\",\"role\":\"ADMIN\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.role").value("USER"))
                .andReturn().getResponse().getContentAsString());
        assertThat(users.findByUsername("new-member").orElseThrow().getRole()).isEqualTo(Role.USER);
        mvc.perform(get("/api/admin/users").header("Authorization", "Bearer " + result.get("token").asText()))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk()).andExpect(jsonPath("$.role").value("ADMIN"))
                .andExpect(jsonPath("$.password").doesNotExist());
        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/admin/users").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.content[0].password").doesNotExist());
    }

    @Test
    void rolesAreReloadedFromDatabaseForExistingJwt() throws Exception {
        User admin = users.findByUsername("admin-test").orElseThrow();
        admin.setRole(Role.USER); users.save(admin);
        mvc.perform(get("/api/admin/dashboard").header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isForbidden());
    }

    @Test
    void postModerationBlocksPublicDetailAndCommentsButRetainsData() throws Exception {
        long id = createPost("FIND_PERSON", "Find an old friend").get("id").asLong();
        createComment(id, true, "I know this friend");
        mvc.perform(get("/api/posts/" + id)).andExpect(status().isOk());
        change("posts", id, "HIDDEN");
        mvc.perform(get("/api/posts")).andExpect(jsonPath("$.length()").value(0));
        mvc.perform(get("/api/posts/" + id)).andExpect(status().isNotFound());
        mvc.perform(get("/api/posts/" + id + "/comments")).andExpect(status().isNotFound());
        mvc.perform(post("/api/posts/" + id + "/comments").contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"new\"}")).andExpect(status().isNotFound());
        mvc.perform(get("/api/admin/posts/" + id).header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("HIDDEN"));
        change("posts", id, "PUBLISHED");
        mvc.perform(get("/api/posts")).andExpect(jsonPath("$.length()").value(1));
        change("posts", id, "DELETED");
        mvc.perform(get("/api/posts/" + id)).andExpect(status().isNotFound());
        assertThat(posts.count()).isEqualTo(1); assertThat(comments.count()).isEqualTo(1);
        change("posts", id, "PUBLISHED");
        mvc.perform(get("/api/posts/" + id)).andExpect(status().isOk());
    }

    @Test
    void commentModerationPreservesAnonymousAndSignedInFlows() throws Exception {
        long id = createPost("CHAT", "Chat").get("id").asLong();
        long commentId = createComment(id, false, "Anonymous reply");
        createComment(id, true, "Member reply");
        mvc.perform(get("/api/posts/" + id + "/comments"))
                .andExpect(jsonPath("$.length()").value(2)).andExpect(jsonPath("$[0].username").isEmpty())
                .andExpect(jsonPath("$[1].username").value("member-test"));
        change("comments", commentId, "HIDDEN");
        mvc.perform(get("/api/posts/" + id + "/comments")).andExpect(jsonPath("$.length()").value(1));
        change("comments", commentId, "PUBLISHED");
        mvc.perform(get("/api/posts/" + id + "/comments")).andExpect(jsonPath("$.length()").value(2));
        change("comments", commentId, "DELETED");
        mvc.perform(get("/api/posts/" + id + "/comments")).andExpect(jsonPath("$.length()").value(1));
        assertThat(comments.count()).isEqualTo(2);
    }

    @Test
    void dashboardCountsTodayAndAllStatusesCorrectly() throws Exception {
        long first = createPost("CHAT", "Yesterday").get("id").asLong();
        Post old = posts.findById(first).orElseThrow(); old.setCreatedAt(LocalDateTime.now().minusDays(1)); posts.save(old);
        long second = createPost("FIND_PERSON", "Today").get("id").asLong();
        long comment = createComment(first, true, "Yesterday reply");
        Comment oldComment = comments.findById(comment).orElseThrow(); oldComment.setCreatedAt(LocalDateTime.now().minusDays(1)); comments.save(oldComment);
        createComment(second, false, "Today reply");
        ordinary.setCreatedAt(LocalDateTime.now().minusDays(1)); users.save(ordinary);
        change("posts", first, "DELETED");
        mvc.perform(get("/api/admin/dashboard").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.totalUsers").value(2)).andExpect(jsonPath("$.totalPosts").value(2))
                .andExpect(jsonPath("$.totalComments").value(2)).andExpect(jsonPath("$.todayNewUsers").value(1))
                .andExpect(jsonPath("$.todayNewPosts").value(1)).andExpect(jsonPath("$.todayNewComments").value(1))
                .andExpect(jsonPath("$.recentPosts.length()").value(2));
    }

    @Test
    void paginationSearchFiltersAndCountsWorkTogether() throws Exception {
        long chat = createPost("CHAT", "Alpha chat").get("id").asLong();
        long find = createPost("FIND_PERSON", "Beta find").get("id").asLong();
        createPost("CHAT", "Gamma chat");
        long comment = createComment(chat, true, "Alpha reply");
        createComment(find, false, "Beta reply");
        change("posts", find, "HIDDEN"); change("comments", comment, "HIDDEN");
        mvc.perform(get("/api/admin/posts").param("size", "1").param("page", "1").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.totalElements").value(3)).andExpect(jsonPath("$.totalPages").value(3))
                .andExpect(jsonPath("$.content.length()").value(1));
        mvc.perform(get("/api/admin/posts").param("search", "beta").param("type", "FIND_PERSON").param("status", "HIDDEN").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.content[0].id").value(find)).andExpect(jsonPath("$.totalElements").value(1));
        mvc.perform(get("/api/admin/comments").param("search", "alpha").param("status", "HIDDEN").param("size", "1").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.totalElements").value(1)).andExpect(jsonPath("$.content[0].postId").value(chat));
        mvc.perform(get("/api/admin/users").param("search", "HESHAN").param("role", "USER").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.totalElements").value(1)).andExpect(jsonPath("$.content[0].postCount").value(3))
                .andExpect(jsonPath("$.content[0].commentCount").value(1));
        mvc.perform(get("/api/admin/users").param("search", "member-test").param("size", "1").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.content[0].username").value("member-test"));
        mvc.perform(get("/api/admin/users/" + ordinary.getId()).header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.postCount").value(3));
        mvc.perform(get("/api/admin/posts").param("search", "%").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.totalElements").value(0));
        mvc.perform(get("/api/admin/comments").param("size", "101").header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/admin/users").param("page", "-1").header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isBadRequest());
        mvc.perform(patch("/api/admin/posts/" + chat + "/status").header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON).content("{}")) .andExpect(status().isBadRequest());
    }

    @Test
    void bootstrapRefusesOrdinaryAccountPromotionAndCreatesNewAdmin() {
        var bootstrap = new DevAdminInitializer(users, passwords, "member-test", "Test-password-123");
        assertThatThrownBy(() -> bootstrap.run(null)).isInstanceOf(IllegalStateException.class);
        assertThat(users.findByUsername("member-test").orElseThrow().getRole()).isEqualTo(Role.USER);
        new DevAdminInitializer(users, passwords, "dev-admin", "Test-password-123").run(null);
        User created = users.findByUsername("dev-admin").orElseThrow();
        assertThat(created.getRole()).isEqualTo(Role.ADMIN);
        assertThat(passwords.matches("Test-password-123", created.getPassword())).isTrue();
        assertThatThrownBy(() -> new DevAdminInitializer(users, passwords, "other", "").run(null))
                .isInstanceOf(IllegalStateException.class);
    }
}
