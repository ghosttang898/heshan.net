package net.tonghehui.backend.geolocation;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import net.tonghehui.backend.comment.CommentRepository;
import net.tonghehui.backend.post.*;
import net.tonghehui.backend.user.*;
import net.tonghehui.backend.security.JwtService;

@SpringBootTest(properties = {"spring.datasource.url=jdbc:h2:mem:location_tests;DB_CLOSE_DELAY=-1",
        "spring.jpa.show-sql=false", "app.admin.bootstrap.enabled=false",
        "app.geolocation.trusted-proxies=10.0.0.2/32"})
@AutoConfigureMockMvc
class IpLocationIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired PostRepository posts;
    @Autowired CommentRepository comments;
    @Autowired UserRepository users;
    @Autowired PasswordEncoder passwords;
    @Autowired JwtService jwt;
    @MockBean IpGeolocationService geolocation;
    private String token;
    private String adminToken;
    private User member;

    @BeforeEach void setup() {
        comments.deleteAll(); posts.deleteAll(); users.deleteAll();
        member = user("location-member", Role.USER); user("location-admin", Role.ADMIN);
        token = jwt.generateToken(member.getUsername()); adminToken = jwt.generateToken("location-admin");
        when(geolocation.locate(any())).thenReturn(IpLocation.unknown(IpLocationStatus.NON_PUBLIC));
    }

    private User user(String username, Role role) {
        var user = new User(); user.setUsername(username); user.setDisplayName("Test"); user.setRole(role);
        user.setPassword(passwords.encode("local-test-password")); return users.save(user);
    }

    private long createPost(String peer, String forwarded) throws Exception {
        String response = mvc.perform(post("/api/posts").with(request -> { request.setRemoteAddr(peer); return request; })
                .header("Authorization", "Bearer " + token).header("X-Forwarded-For", forwarded)
                .contentType(MediaType.APPLICATION_JSON).content("""
                {"title":"Location test","content":"Community","type":"CHAT", "ipCountryCode":"XX",
                 "ipCountry":"Forged", "ipCity":"Fake", "ipRegion":"Fake", "ipLocationStatus":"RESOLVED",
                 "ipLocation":{"country":"Forged"}, "ip":"1.1.1.1"}
                """))
                .andExpect(status().isOk()).andExpect(jsonPath("$.ip").doesNotExist())
                .andExpect(jsonPath("$.clientIp").doesNotExist()).andReturn().getResponse().getContentAsString();
        assertThat(response).doesNotContain("Forged", "Fake", peer, forwarded);
        return json.readTree(response).get("id").asLong();
    }

    @Test void serverSnapshotOverridesSpoofedFieldsAndUntrustedHeaders() throws Exception {
        var location = new IpLocation("US", "美国", "Pennsylvania", "Philadelphia", IpLocationStatus.RESOLVED);
        when(geolocation.locate("8.8.8.8")).thenReturn(location);
        long id = createPost("8.8.8.8", "1.1.1.1");
        assertThat(posts.findById(id).orElseThrow().getIpCity()).isEqualTo("Philadelphia");
        mvc.perform(post("/api/posts/" + id + "/comments").with(request -> { request.setRemoteAddr("8.8.8.8"); return request; })
                .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"Anonymous\",\"ipCountry\":\"Forged\",\"ipCity\":\"Fake\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.ipCountry").value("美国"))
                .andExpect(jsonPath("$.ipCity").value("Philadelphia")).andExpect(jsonPath("$.username").isEmpty())
                .andExpect(jsonPath("$.ip").doesNotExist());
        clearInvocations(geolocation);
        mvc.perform(get("/api/posts/" + id)).andExpect(jsonPath("$.ipCity").value("Philadelphia"));
        mvc.perform(get("/api/posts/" + id + "/comments")).andExpect(jsonPath("$[0].ipCity").value("Philadelphia"));
        mvc.perform(get("/api/admin/posts").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.content[0].ipRegion").value("Pennsylvania"));
        mvc.perform(get("/api/admin/comments").header("Authorization", "Bearer " + adminToken))
                .andExpect(jsonPath("$.content[0].ipLocationStatus").value("RESOLVED"));
        mvc.perform(patch("/api/admin/posts/" + id + "/status").header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"HIDDEN\",\"ipCountry\":\"Forged\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.ipCountry").value("美国"));
        verifyNoInteractions(geolocation);
    }

    @Test void trustedProxyUsesVpnExitAndNeverTheClaimedLeftmostIp() throws Exception {
        when(geolocation.locate("8.8.8.8")).thenReturn(new IpLocation("US", "美国", null, null, IpLocationStatus.RESOLVED));
        long id = createPost("10.0.0.2", "114.114.114.114, 8.8.8.8");
        assertThat(posts.findById(id).orElseThrow().getIpCountryCode()).isEqualTo("US");
        verify(geolocation).locate("8.8.8.8"); verify(geolocation, never()).locate("114.114.114.114");
    }

    @Test void failedLocationAndLocalhostDoNotBlockPostingOrSignedInComments() throws Exception {
        when(geolocation.locate("8.8.8.8")).thenReturn(IpLocation.unknown(IpLocationStatus.TIMEOUT));
        long id = createPost("8.8.8.8", "1.1.1.1");
        assertThat(posts.findById(id).orElseThrow().getIpLocationStatus()).isEqualTo(IpLocationStatus.TIMEOUT);
        mvc.perform(post("/api/posts/" + id + "/comments").header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"Local comment\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.ipLocationStatus").value("NON_PUBLIC"))
                .andExpect(jsonPath("$.username").value("location-member"));
        createPost("127.0.0.1", "8.8.8.8");
    }

    @Test void historicalContentStaysUnknownAndUserProfilesHaveNoLocation() throws Exception {
        var old = new Post(); old.setAuthor(member); old.setTitle("Historical"); old.setContent("Old"); old.setType(PostType.CHAT);
        old = posts.save(old);
        mvc.perform(get("/api/posts/" + old.getId())).andExpect(jsonPath("$.ipCountry").isEmpty())
                .andExpect(jsonPath("$.ipLocationStatus").value("UNKNOWN"));
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + token))
                .andExpect(jsonPath("$.ipCountry").doesNotExist()).andExpect(jsonPath("$.ip").doesNotExist());
        verifyNoInteractions(geolocation);
    }
}
