package net.tonghehui.backend.security;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import io.jsonwebtoken.io.Decoders;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Profiles;

/** Fail before connecting to or migrating an incorrectly configured production database. */
public class ProductionEnvironmentGuard implements EnvironmentPostProcessor, Ordered {
    @Override public int getOrder() { return ConfigDataEnvironmentPostProcessor.ORDER + 1; }

    @Override public void postProcessEnvironment(ConfigurableEnvironment env, SpringApplication application) {
        if (!env.acceptsProfiles(Profiles.of("prod"))) return;
        require(!env.acceptsProfiles(Profiles.of("dev")), "prod and dev cannot be combined");
        require(env.getProperty("spring.datasource.url", "").startsWith("jdbc:postgresql://"), "prod requires PostgreSQL");
        require("org.postgresql.Driver".equals(env.getProperty("spring.datasource.driver-class-name")), "prod requires PostgreSQL driver");
        require(!env.getProperty("spring.datasource.username", "").isBlank()
                && !"postgres".equals(env.getProperty("spring.datasource.username")), "A dedicated application database role is required");
        require(!env.getProperty("spring.datasource.password", "").isBlank(), "Production database password is required");
        require("validate".equals(env.getProperty("spring.jpa.hibernate.ddl-auto")), "prod requires Hibernate validate");
        require(env.getProperty("spring.flyway.enabled", Boolean.class, false), "prod requires Flyway");
        require(env.getProperty("spring.flyway.clean-disabled", Boolean.class, false), "Flyway clean must be disabled");
        require(env.getProperty("spring.flyway.validate-on-migrate", Boolean.class, false), "Flyway validation is required");
        require(!env.getProperty("spring.flyway.out-of-order", Boolean.class, false), "Out-of-order migrations are forbidden");
        require(!env.getProperty("spring.flyway.baseline-on-migrate", Boolean.class, false), "Automatic Flyway baselining is forbidden");
        require(!env.getProperty("spring.h2.console.enabled", Boolean.class, false), "H2 console is forbidden in prod");
        require(!env.getProperty("app.admin.bootstrap.enabled", Boolean.class, false), "Development admin initialization is forbidden");
        Object supplied = env.getSystemEnvironment().get("APP_JWT_SECRET");
        require(supplied instanceof String && !((String) supplied).isBlank(), "APP_JWT_SECRET must be supplied through the environment");
        String secret = (String) supplied;
        require(!secret.equals("TongHeHuiSecretKeyTongHeHuiSecretKey1234567890"), "Development JWT secret is forbidden");
        require(secret.equals(env.getProperty("app.jwt.secret")), "JWT configuration must use APP_JWT_SECRET");
        byte[] bytes;
        try { bytes = Decoders.BASE64.decode(secret); }
        catch (io.jsonwebtoken.io.DecodingException | IllegalArgumentException exception) { bytes = secret.getBytes(StandardCharsets.UTF_8); }
        require(bytes.length >= 32, "JWT signing key must contain at least 32 bytes");
        String origins = env.getProperty("app.cors.allowed-origins", "");
        require(!origins.isBlank(), "Explicit frontend CORS origins are required");
        Arrays.stream(origins.split(",", -1)).forEach(value -> {
            try {
                URI origin = URI.create(value.trim());
                require("https".equals(origin.getScheme()) && origin.getHost() != null
                        && origin.getRawUserInfo() == null && origin.getRawQuery() == null
                        && origin.getRawFragment() == null && origin.getRawPath().isEmpty()
                        && !value.contains("*"), "CORS origins must be exact HTTPS origins");
            } catch (IllegalArgumentException exception) {
                throw new IllegalStateException("Invalid production CORS origin");
            }
        });
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
