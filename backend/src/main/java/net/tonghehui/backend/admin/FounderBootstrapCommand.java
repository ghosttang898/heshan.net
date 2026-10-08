package net.tonghehui.backend.admin;

import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Profile;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import net.tonghehui.backend.user.UserRepository;

public final class FounderBootstrapCommand {
    private FounderBootstrapCommand() {}

    public static void run(String[] args) {
        var arguments = new DefaultApplicationArguments(args);
        Long id = Long.valueOf(option(arguments, "founder-id"));
        String username = option(arguments, "founder-username");
        Long confirmedId = Long.valueOf(option(arguments, "confirm-founder-id"));
        String confirmedUsername = option(arguments, "confirm-founder-username");
        var application = new SpringApplication(BootstrapConfiguration.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setAdditionalProfiles("founder-bootstrap");
        try (var context = application.run(args)) {
            context.getBean(FounderBootstrapService.class).initialize(id, username, confirmedId, confirmedUsername);
            System.out.println("Founder initialization completed for confirmed user ID " + id);
        }
    }

    private static String option(DefaultApplicationArguments args, String key) {
        var values = args.getOptionValues(key);
        if (values == null || values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException("Exactly one --" + key + " is required");
        }
        return values.get(0);
    }

    @Configuration
    @Profile("founder-bootstrap")
    @EnableAutoConfiguration(exclude = SecurityAutoConfiguration.class)
    @EntityScan("net.tonghehui.backend")
    @EnableJpaRepositories(basePackageClasses = {UserRepository.class, FounderIdentityRepository.class})
    @Import(FounderBootstrapService.class)
    public static class BootstrapConfiguration {}
}
