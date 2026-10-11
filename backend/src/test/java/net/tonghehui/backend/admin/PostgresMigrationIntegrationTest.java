package net.tonghehui.backend.admin;

import static org.assertj.core.api.Assertions.*;
import java.sql.DriverManager;
import java.nio.file.Path;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.MountableFile;
import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;

@Testcontainers(disabledWithoutDocker = true)
class PostgresMigrationIntegrationTest {
    private static final String APP_USER = "migration_app";
    private static final String APP_PASSWORD = "isolated-fixture-quote'backslash\\-123";
    @Container static final PostgreSQLContainer<?> database = new PostgreSQLContainer<>("postgres:16-bookworm")
            .withEnv("APP_DB_USER", APP_USER).withEnv("APP_DB_PASSWORD", APP_PASSWORD)
            .withCopyFileToContainer(MountableFile.forHostPath(Path.of(System.getProperty("basedir", "."),
                    "../deploy/postgres-init.sh").normalize(), 0644), "/docker-entrypoint-initdb.d/10-app-user.sh");
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
