package net.tonghehui.backend.admin;

import static org.assertj.core.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import net.tonghehui.backend.user.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

class FounderBootstrapTest {
    @TempDir Path directory;

    @Test void offlineCommandUsesConfirmedIdentityIsOneTimeAndPersistsAudit() throws Exception {
        String url = "jdbc:h2:file:" + directory.resolve("owner-test");
        var app = new SpringApplication(FounderBootstrapCommand.BootstrapConfiguration.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setAdditionalProfiles("founder-bootstrap");
        Long id;
        try (var context = app.run("--spring.datasource.url=" + url, "--spring.jpa.show-sql=false")) {
            var users = context.getBean(UserRepository.class);
            var owner = new User(); owner.setUsername("ghost"); owner.setDisplayName("Isolated test owner");
            owner.setPassword("unused-test-fixture"); owner.setRole(Role.USER); id = users.saveAndFlush(owner).getId();
            var service = context.getBean(FounderBootstrapService.class);
            assertThatThrownBy(() -> service.initialize(id, "ghost", id + 1, "ghost")).isInstanceOf(IllegalArgumentException.class);
            assertThatThrownBy(() -> service.initialize(id + 1, "ghost", id + 1, "ghost")).isInstanceOf(IllegalArgumentException.class);
            owner.setUsername("not-ghost"); users.saveAndFlush(owner);
            assertThatThrownBy(() -> service.initialize(id, "ghost", id, "ghost")).isInstanceOf(IllegalArgumentException.class);
            assertThat(users.findById(id).orElseThrow().getRole()).isEqualTo(Role.USER);
            owner.setUsername("ghost"); users.saveAndFlush(owner);
        }
        FounderBootstrapCommand.run(new String[]{"--initialize-founder", "--spring.datasource.url=" + url,
                "--spring.jpa.show-sql=false", "--founder-id=" + id, "--founder-username=ghost",
                "--confirm-founder-id=" + id, "--confirm-founder-username=ghost"});
        try (var context = app.run("--spring.datasource.url=" + url, "--spring.jpa.show-sql=false")) {
            assertThat(context.getBean(UserRepository.class).findById(id).orElseThrow().getRole()).isEqualTo(Role.SUPER_ADMIN);
            assertThat(context.getBean(FounderIdentityRepository.class).findById(1L).orElseThrow().getUserId()).isEqualTo(id);
            var audits = context.getBean(RoleChangeAuditRepository.class).findAll();
            assertThat(audits).hasSize(1);
            assertThat(audits.get(0).getAction()).isEqualTo(RoleChangeAudit.Action.INITIALIZE_FOUNDER);
            assertThat(audits.get(0).getActorId()).isEqualTo(id);
            assertThatThrownBy(() -> context.getBean(FounderBootstrapService.class).initialize(id, "ghost", id, "ghost"))
                    .isInstanceOf(IllegalStateException.class).hasMessageContaining("already");
        }
        assertThat(Files.exists(directory.resolve("owner-test.mv.db"))).isTrue();
    }
}
