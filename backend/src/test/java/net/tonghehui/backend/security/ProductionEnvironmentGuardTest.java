package net.tonghehui.backend.security;

import static org.assertj.core.api.Assertions.*;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class ProductionEnvironmentGuardTest {
    private static final String TEST_SECRET = "test-fixture-key-not-for-deployment-0123456789";
    private Map<String, Object> properties() {
        var values = new HashMap<String, Object>();
        values.put("spring.datasource.url", "jdbc:postgresql://localhost/test");
        values.put("spring.datasource.driver-class-name", "org.postgresql.Driver");
        values.put("spring.datasource.username", "test_app");
        values.put("spring.datasource.password", "isolated-test-only");
        values.put("spring.jpa.hibernate.ddl-auto", "validate");
        values.put("spring.flyway.enabled", true);
        values.put("spring.flyway.clean-disabled", true);
        values.put("spring.flyway.validate-on-migrate", true);
        values.put("app.jwt.secret", TEST_SECRET);
        values.put("app.cors.allowed-origins", "https://test.pages.dev,https://heshan.net");
        return values;
    }
    private StandardEnvironment environment(Map<String, Object> values, Map<String, Object> secrets) {
        var env = new StandardEnvironment() {
            @Override public Map<String, Object> getSystemEnvironment() { return secrets; }
        };
        env.setActiveProfiles("prod");
        env.getPropertySources().addFirst(new MapPropertySource("test", values));
        return env;
    }
    private void check(Map<String, Object> values, Map<String, Object> secrets) {
        new ProductionEnvironmentGuard().postProcessEnvironment(environment(values, secrets), null);
    }
    @Test void guardIsRegisteredAfterConfigurationLoading() {
        assertThat(org.springframework.core.io.support.SpringFactoriesLoader.loadFactoryNames(
                org.springframework.boot.env.EnvironmentPostProcessor.class, getClass().getClassLoader()))
                .contains(ProductionEnvironmentGuard.class.getName());
        assertThat(new ProductionEnvironmentGuard().getOrder())
                .isGreaterThan(org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor.ORDER);
    }
    @Test void validProductionAndDevelopmentConfigurations() {
        assertThatCode(() -> check(properties(), Map.of("APP_JWT_SECRET", TEST_SECRET))).doesNotThrowAnyException();
        var env = environment(Map.of(), Map.of()); env.setActiveProfiles("dev");
        assertThatCode(() -> new ProductionEnvironmentGuard().postProcessEnvironment(env, null)).doesNotThrowAnyException();
    }
    @Test void unsafeOverridesAreRejectedBeforeDatabaseStartup() {
        for (var entry : Map.<String, Object>of(
                "spring.datasource.url", "jdbc:h2:mem:unsafe",
                "spring.datasource.driver-class-name", "org.h2.Driver",
                "spring.jpa.hibernate.ddl-auto", "update",
                "spring.flyway.enabled", false,
                "spring.flyway.clean-disabled", false,
                "spring.flyway.baseline-on-migrate", true,
                "app.admin.bootstrap.enabled", true,
                "spring.h2.console.enabled", true,
                "app.cors.allowed-origins", "*").entrySet()) {
            var values = properties(); values.put(entry.getKey(), entry.getValue());
            assertThatThrownBy(() -> check(values, Map.of("APP_JWT_SECRET", TEST_SECRET))).isInstanceOf(IllegalStateException.class);
        }
        var env = environment(properties(), Map.of("APP_JWT_SECRET", TEST_SECRET)); env.setActiveProfiles("prod", "dev");
        assertThatThrownBy(() -> new ProductionEnvironmentGuard().postProcessEnvironment(env, null)).isInstanceOf(IllegalStateException.class);
    }
    @Test void missingWeakDefaultAndOverriddenSecretsAreRejected() {
        assertThatThrownBy(() -> check(properties(), Map.of())).isInstanceOf(IllegalStateException.class);
        for (String secret : new String[]{"short", "TongHeHuiSecretKeyTongHeHuiSecretKey1234567890"}) {
            var values = properties(); values.put("app.jwt.secret", secret);
            assertThatThrownBy(() -> check(values, Map.of("APP_JWT_SECRET", secret))).isInstanceOf(IllegalStateException.class);
        }
        var values = properties(); values.put("app.jwt.secret", "overridden");
        assertThatThrownBy(() -> check(values, Map.of("APP_JWT_SECRET", TEST_SECRET))).isInstanceOf(IllegalStateException.class);
    }
}
