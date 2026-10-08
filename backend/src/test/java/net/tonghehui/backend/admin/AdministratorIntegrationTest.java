package net.tonghehui.backend.admin;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import net.tonghehui.backend.user.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.SpyBean;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import java.util.Map;

@SpringBootTest(properties = {"spring.datasource.url=jdbc:h2:mem:administrator_tests;DB_CLOSE_DELAY=-1",
        "spring.jpa.show-sql=false", "app.admin.bootstrap.enabled=false"})
@AutoConfigureMockMvc
class AdministratorIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired UserRepository users;
    @Autowired net.tonghehui.backend.post.PostRepository posts;
    @Autowired net.tonghehui.backend.comment.CommentRepository comments;
    @Autowired FounderIdentityRepository founders;
    @Autowired FounderBootstrapService bootstrap;
    @Autowired PasswordEncoder passwords;
    @SpyBean RoleChangeAuditRepository audits;
    User owner, admin, member;
    String ownerToken, adminToken, memberToken;

    @BeforeEach void setup() throws Exception {
        founders.deleteAll(); audits.deleteAll(); comments.deleteAll(); posts.deleteAll(); users.deleteAll();
        owner = create("test-owner", Role.SUPER_ADMIN);
        admin = create("test-admin", Role.ADMIN);
        member = create("test-member", Role.USER);
        ownerToken = login(owner); adminToken = login(admin); memberToken = login(member);
    }

    User create(String username, Role role) {
        User user = new User(); user.setUsername(username); user.setDisplayName(username);
        user.setRole(role); user.setPassword(passwords.encode("test-password-123"));
        return users.save(user);
    }

    String login(User user) throws Exception {
        var result = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", user.getUsername(), "password", "test-password-123"))))
                .andExpect(status().isOk()).andReturn();
        return json.readTree(result.getResponse().getContentAsString()).get("token").asText();
    }

    ResultActions change(String token, User target, Role role, Role expected) throws Exception {
        return mvc.perform(patch("/api/admin/users/" + target.getId() + "/role")
                .header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("role", role, "expectedRole", expected))));
    }

    @Test void threeRolesAndRegistrationAreEnforced() throws Exception {
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"ghost\",\"displayName\":\"Owner?\",\"password\":\"test123\",\"role\":\"SUPER_ADMIN\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.role").value("USER"));
        assertThat(users.findByUsername("ghost").orElseThrow().getRole()).isEqualTo(Role.USER);
        mvc.perform(get("/api/admin/dashboard")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/admin/dashboard").header("Authorization", "Bearer " + memberToken)).andExpect(status().isForbidden());
        for (String token : new String[]{adminToken, ownerToken}) {
            for (String path : new String[]{"dashboard", "posts", "comments", "users"}) {
                mvc.perform(get("/api/admin/" + path).header("Authorization", "Bearer " + token)).andExpect(status().isOk());
            }
        }
    }

    @Test void onlySuperAdminCanReadOrModifyAdministrators() throws Exception {
        mvc.perform(get("/h2-console/").header("Authorization", "Bearer " + adminToken)).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/administrators")).andExpect(status().isUnauthorized());
        for (String token : new String[]{adminToken, memberToken}) {
            mvc.perform(get("/api/admin/administrators").header("Authorization", "Bearer " + token)).andExpect(status().isForbidden());
            change(token, member, Role.ADMIN, Role.USER).andExpect(status().isForbidden());
            change(token, admin, Role.USER, Role.ADMIN).andExpect(status().isForbidden());
            change(token, owner, Role.USER, Role.SUPER_ADMIN).andExpect(status().isForbidden());
        }
        mvc.perform(get("/api/admin/administrators").header("Authorization", "Bearer " + ownerToken))
                .andExpect(status().isOk()).andExpect(jsonPath("$.totalElements").value(2));
        mvc.perform(get("/api/admin/administrators").param("search", "test-admin").param("role", "ADMIN")
                .param("size", "1").header("Authorization", "Bearer " + ownerToken))
                .andExpect(jsonPath("$.content[0].id").value(admin.getId())).andExpect(jsonPath("$.totalElements").value(1));
        assertThat(audits.count()).isZero();
    }

    @Test void bothAdministratorLevelsCanModeratePostsAndComments() throws Exception {
        var postResult = mvc.perform(post("/api/posts").header("Authorization", "Bearer " + memberToken)
                .contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"Role test\",\"content\":\"Community\",\"type\":\"CHAT\"}"))
                .andExpect(status().isOk()).andReturn();
        long postId = json.readTree(postResult.getResponse().getContentAsString()).get("id").asLong();
        var commentResult = mvc.perform(post("/api/posts/" + postId + "/comments").header("Authorization", "Bearer " + memberToken)
                .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"Reply\"}"))
                .andExpect(status().isOk()).andReturn();
        long commentId = json.readTree(commentResult.getResponse().getContentAsString()).get("id").asLong();
        for (String token : new String[]{adminToken, ownerToken}) {
            for (String path : new String[]{"posts/" + postId, "comments/" + commentId}) {
                mvc.perform(patch("/api/admin/" + path + "/status").header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"HIDDEN\"}"))
                        .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("HIDDEN"));
                mvc.perform(patch("/api/admin/" + path + "/status").header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"PUBLISHED\"}"))
                        .andExpect(status().isOk());
            }
        }
        mvc.perform(get("/api/posts/" + postId)).andExpect(status().isOk());
        mvc.perform(get("/api/posts/" + postId + "/comments")).andExpect(jsonPath("$.length()").value(1));
    }

    @Test void grantsRevocationsAndOldJwtUseCurrentDatabaseRoleAndHaveAudits() throws Exception {
        change(ownerToken, member, Role.ADMIN, Role.USER).andExpect(status().isOk()).andExpect(jsonPath("$.role").value("ADMIN"));
        mvc.perform(get("/api/admin/posts").header("Authorization", "Bearer " + memberToken)).andExpect(status().isOk());
        change(ownerToken, member, Role.USER, Role.ADMIN).andExpect(status().isOk());
        mvc.perform(get("/api/admin/posts").header("Authorization", "Bearer " + memberToken)).andExpect(status().isForbidden());
        change(ownerToken, admin, Role.USER, Role.ADMIN).andExpect(status().isOk());
        mvc.perform(get("/api/admin/comments").header("Authorization", "Bearer " + adminToken)).andExpect(status().isForbidden());
        assertThat(audits.findAll()).hasSize(3).allSatisfy(audit -> {
            assertThat(audit.getActorId()).isEqualTo(owner.getId());
            assertThat(audit.getCreatedAt()).isNotNull();
            assertThat(audit.getTargetUserId()).isIn(member.getId(), admin.getId());
            assertThat(audit.getNewRole()).isNotEqualTo(audit.getOldRole());
        });
        assertThat(audits.findAll().get(0).getAction()).isEqualTo(RoleChangeAudit.Action.GRANT_ADMIN);
        assertThat(audits.findAll().get(1).getAction()).isEqualTo(RoleChangeAudit.Action.REVOKE_ADMIN);
    }

    @Test void illegalTransitionsAndStaleConfirmationCannotChangeRoles() throws Exception {
        for (User target : new User[]{member, admin, owner}) {
            change(ownerToken, target, Role.SUPER_ADMIN, target.getRole()).andExpect(status().isBadRequest());
        }
        change(ownerToken, owner, Role.ADMIN, Role.SUPER_ADMIN).andExpect(status().isForbidden());
        change(ownerToken, owner, Role.USER, Role.SUPER_ADMIN).andExpect(status().isForbidden());
        change(ownerToken, member, Role.ADMIN, Role.ADMIN).andExpect(status().isConflict());
        change(ownerToken, member, Role.USER, Role.USER).andExpect(status().isConflict());
        mvc.perform(patch("/api/admin/users/" + member.getId() + "/role").header("Authorization", "Bearer " + ownerToken)
                .contentType(MediaType.APPLICATION_JSON).content("{\"role\":\"ADMIN\"}"))
                .andExpect(status().isBadRequest());
        assertThat(audits.count()).isZero();
    }

    @Test void protectedFounderIdIsIndependentOfUsernameAndEvenRole() throws Exception {
        founders.saveAndFlush(new FounderIdentity(admin.getId()));
        admin.setUsername("renamed-founder"); users.saveAndFlush(admin);
        change(ownerToken, admin, Role.USER, Role.ADMIN).andExpect(status().isForbidden());
        assertThat(users.findById(admin.getId()).orElseThrow().getRole()).isEqualTo(Role.ADMIN);
        assertThat(audits.count()).isZero();
    }

    @Test void accountMutationAndAuditWritesHaveNoWebApi() throws Exception {
        for (String suffix : new String[]{"", "/status", "/ban"}) {
            mvc.perform(patch("/api/admin/users/" + owner.getId() + suffix).header("Authorization", "Bearer " + adminToken)
                    .contentType(MediaType.APPLICATION_JSON).content("{\"role\":\"USER\",\"banned\":true}"))
                    .andExpect(status().is4xxClientError());
        }
        mvc.perform(delete("/api/admin/users/" + owner.getId()).header("Authorization", "Bearer " + adminToken))
                .andExpect(status().is4xxClientError());
        mvc.perform(delete("/api/admin/role-audits/1").header("Authorization", "Bearer " + memberToken))
                .andExpect(status().isForbidden());
        assertThat(users.findById(owner.getId()).orElseThrow().getRole()).isEqualTo(Role.SUPER_ADMIN);
    }

    @Test void auditFailureRollsBackRoleChange() {
        doThrow(new IllegalStateException("simulated audit storage failure")).when(audits).save(any(RoleChangeAudit.class));
        assertThatThrownBy(() -> change(ownerToken, member, Role.ADMIN, Role.USER)).hasRootCauseInstanceOf(IllegalStateException.class);
        assertThat(users.findById(member.getId()).orElseThrow().getRole()).isEqualTo(Role.USER);
        assertThat(audits.count()).isZero();
    }

    @Test void founderInitializationRefusesInMemoryDatabase() {
        assertThatThrownBy(() -> bootstrap.initialize(member.getId(), "ghost", member.getId(), "ghost"))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("persistent");
        assertThat(users.findById(member.getId()).orElseThrow().getRole()).isEqualTo(Role.USER);
        assertThat(founders.count()).isZero();
    }
}
