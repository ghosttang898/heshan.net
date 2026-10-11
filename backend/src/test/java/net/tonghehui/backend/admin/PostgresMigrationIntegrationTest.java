package net.tonghehui.backend.admin;

import static org.assertj.core.api.Assertions.*;
import java.sql.DriverManager;
import java.nio.file.Path;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Map;
import com.github.dockerjava.api.model.ExposedPort;
import com.github.dockerjava.api.model.PortBinding;
import com.github.dockerjava.api.model.Ports;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.core.env.StandardEnvironment;
import net.tonghehui.backend.TongHeHuiApplication;
import tools.jackson.databind.ObjectMapper;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.MountableFile;
import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;

@Testcontainers
class PostgresMigrationIntegrationTest {
    private static final String APP_USER = "migration_app";
    private static final String APP_PASSWORD = "isolated-fixture-quote'backslash\\-123";
    @Container static final PostgreSQLContainer<?> database = isolatedDatabase();

    private static PostgreSQLContainer<?> isolatedDatabase() {
        return new PostgreSQLContainer<>("postgres:16-bookworm")
                .withEnv("APP_DB_USER", APP_USER).withEnv("APP_DB_PASSWORD", APP_PASSWORD)
                .withCommand("postgres", "-c", "shared_buffers=64MB", "-c", "max_connections=20")
                .withCopyFileToContainer(MountableFile.forHostPath(Path.of(System.getProperty("basedir", "."),
                        "../deploy/postgres-init.sh").normalize(), 0644), "/docker-entrypoint-initdb.d/10-app-user.sh")
                .withCreateContainerCmdModifier(command -> command.getHostConfig()
                        .withMemory(384L * 1024 * 1024)
                        .withPortBindings(new PortBinding(Ports.Binding.bindIp("127.0.0.1"), new ExposedPort(5432))));
    }

    @Test void productionProfileAutoMigratesServesAuthenticatedRequestsAndPersistsFounder() throws Exception {
        try (var production = isolatedDatabase()) {
            production.start();
            byte[] key = new byte[48]; new SecureRandom().nextBytes(key);
            Map<String, Object> fixtureEnvironment = Map.of("APP_JWT_SECRET", Base64.getEncoder().encodeToString(key),
                    "DB_URL", production.getJdbcUrl(), "DB_USER", APP_USER, "DB_PASSWORD", APP_PASSWORD,
                    "APP_CORS_ALLOWED_ORIGINS", "https://isolated-test.invalid");
            var application = new SpringApplication(TongHeHuiApplication.class);
            // An isolated environment fixture exercises the same prod startup guard and configuration loading.
            application.setEnvironment(new StandardEnvironment() {
                @Override public Map<String, Object> getSystemEnvironment() { return fixtureEnvironment; }
            });
            application.setAdditionalProfiles("prod");
            String[] args = {"--server.address=127.0.0.1", "--server.port=0", "--spring.main.banner-mode=off", "--logging.level.root=ERROR"};
            Long id;
            String username = "production-fixture-owner";
            try (var context = application.run(args)) {
                context.getBean(Flyway.class).validate();
                assertThat(context.getBean(Flyway.class).info().applied()).hasSize(1);
                int port = context.getEnvironment().getRequiredProperty("local.server.port", Integer.class);
                String base = "http://127.0.0.1:" + port;
                var client = HttpClient.newHttpClient();
                assertThat(client.send(HttpRequest.newBuilder(URI.create(base + "/actuator/health")).build(),
                        HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(200);
                var registration = client.send(HttpRequest.newBuilder(URI.create(base + "/api/auth/register"))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString("{\"username\":\"" + username
                                + "\",\"displayName\":\"Fixture\",\"password\":\"isolated-fixture-password\",\"role\":\"SUPER_ADMIN\"}")).build(),
                        HttpResponse.BodyHandlers.ofString());
                assertThat(registration.statusCode()).isEqualTo(200);
                var json = context.getBean(ObjectMapper.class);
                var registered = json.readTree(registration.body());
                assertThat(registered.get("role").asText()).isEqualTo("USER");
                String token = registered.get("token").asText();
                var adminRequest = HttpRequest.newBuilder(URI.create(base + "/api/admin/dashboard"))
                        .header("Authorization", "Bearer " + token).build();
                assertThat(client.send(adminRequest, HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(403);
                id = context.getBean(UserRepository.class).findByUsername(username).orElseThrow().getId();
                var founder = context.getBean(FounderBootstrapService.class);
                assertThatThrownBy(() -> founder.initialize(id, username, id + 1, username)).isInstanceOf(IllegalArgumentException.class);
                founder.initialize(id, username, id, username);
                assertThat(client.send(adminRequest, HttpResponse.BodyHandlers.ofString()).statusCode()).isEqualTo(200);
                assertThat(context.getBean(RoleChangeAuditRepository.class).count()).isEqualTo(1);
                assertThatThrownBy(() -> founder.initialize(id, username, id, username)).isInstanceOf(IllegalStateException.class);
            }
            try (var restarted = application.run(args)) {
                assertThat(restarted.getBean(UserRepository.class).findById(id).orElseThrow().getRole()).isEqualTo(Role.SUPER_ADMIN);
                assertThat(restarted.getBean(FounderIdentityRepository.class).findById(1L).orElseThrow().getUserId()).isEqualTo(id);
                assertThat(restarted.getBean(Flyway.class).info().applied()).hasSize(1);
            }
        }
    }
    @Test void migrateValidatePreserveRowsAndInitializeFounderOnce() throws Exception {
        var flyway = Flyway.configure().dataSource(database.getJdbcUrl(), APP_USER, APP_PASSWORD)
                .locations("classpath:db/migration/postgresql").cleanDisabled(true).load();
        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(1);
        flyway.validate();
        var application = new SpringApplication(FounderBootstrapCommand.BootstrapConfiguration.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setAdditionalProfiles("founder-bootstrap");
        String[] args = {"--spring.datasource.url=" + database.getJdbcUrl(),
                "--spring.datasource.driver-class-name=org.postgresql.Driver",
                "--spring.datasource.username=" + APP_USER,
                "--spring.datasource.password=" + APP_PASSWORD,
                "--spring.jpa.hibernate.ddl-auto=validate", "--spring.jpa.show-sql=false"};
        Long id;
        try (var context = application.run(args)) {
            var users = context.getBean(UserRepository.class);
            var user = new User(); user.setUsername("ghost"); user.setDisplayName("Migration test owner");
            user.setPassword("unused-isolated-fixture"); id = users.saveAndFlush(user).getId();
            assertThat(user.getRole()).isEqualTo(Role.USER);
            var bootstrap = context.getBean(FounderBootstrapService.class);
            assertThatThrownBy(() -> bootstrap.initialize(id, "ghost", id + 1, "ghost")).isInstanceOf(IllegalArgumentException.class);
            bootstrap.initialize(id, "ghost", id, "ghost");
            assertThat(users.findById(id).orElseThrow().getRole()).isEqualTo(Role.SUPER_ADMIN);
            assertThat(context.getBean(RoleChangeAuditRepository.class).count()).isEqualTo(1);
            assertThatThrownBy(() -> bootstrap.initialize(id, "ghost", id, "ghost")).isInstanceOf(IllegalStateException.class);
        }
        try (var connection = DriverManager.getConnection(database.getJdbcUrl(), APP_USER, APP_PASSWORD);
                var statement = connection.createStatement()) {
            statement.executeUpdate("INSERT INTO posts(title,content,type,author_id,created_at) VALUES ('historical','keep content','CHAT'," + id + ",CURRENT_TIMESTAMP)");
            statement.executeUpdate("INSERT INTO comments(content,post_id,created_at) SELECT 'anonymous historical reply', id, CURRENT_TIMESTAMP FROM posts");
        }
        assertThat(flyway.migrate().migrationsExecuted).isZero();
        try (var connection = DriverManager.getConnection(database.getJdbcUrl(), APP_USER, APP_PASSWORD);
                var statement = connection.createStatement()) {
            try (var rows = statement.executeQuery("SELECT username, role FROM users WHERE id=" + id)) {
                assertThat(rows.next()).isTrue(); assertThat(rows.getString(1)).isEqualTo("ghost");
                assertThat(rows.getString(2)).isEqualTo("SUPER_ADMIN");
            }
            assertThatThrownBy(() -> statement.executeUpdate("INSERT INTO users(username,password,display_name,role,created_at) VALUES ('another-owner','fixture','fixture','SUPER_ADMIN',CURRENT_TIMESTAMP)"))
                    .isInstanceOf(java.sql.SQLException.class);
            try (var rows = statement.executeQuery("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=CURRENT_USER")) {
                assertThat(rows.next()).isTrue();
                assertThat(rows.getBoolean(1)).isFalse(); assertThat(rows.getBoolean(2)).isFalse(); assertThat(rows.getBoolean(3)).isFalse();
            }
            try (var rows = statement.executeQuery("SELECT content, ip_location_status FROM posts")) {
                assertThat(rows.next()).isTrue(); assertThat(rows.getString(1)).isEqualTo("keep content"); assertThat(rows.getString(2)).isNull();
            }
            try (var rows = statement.executeQuery("SELECT content, user_id FROM comments")) {
                assertThat(rows.next()).isTrue(); assertThat(rows.getString(1)).isEqualTo("anonymous historical reply"); assertThat(rows.getObject(2)).isNull();
            }
        }
    }
}
