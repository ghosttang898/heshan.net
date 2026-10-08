package net.tonghehui.backend.admin;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;

@Component
@Profile("dev")
@ConditionalOnProperty(name = "app.admin.bootstrap.enabled", havingValue = "true")
public class DevAdminInitializer implements ApplicationRunner {
    private final UserRepository users;
    private final PasswordEncoder passwords;
    private final String username;
    private final String password;

    public DevAdminInitializer(UserRepository users, PasswordEncoder passwords,
            @Value("${app.admin.bootstrap.username:}") String username,
            @Value("${app.admin.bootstrap.password:}") String password) {
        this.users = users;
        this.passwords = passwords;
        this.username = username.trim();
        this.password = password;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (username.isBlank() || password.isBlank() || password.length() < 12) {
            throw new IllegalStateException("Admin bootstrap requires username and password of at least 12 characters");
        }
        User existing = users.findByUsername(username).orElse(null);
        if (existing != null) {
            if (existing.getRole() != Role.ADMIN) {
                throw new IllegalStateException("Admin bootstrap will not promote an existing ordinary account");
            }
            return;
        }
        User admin = new User();
        admin.setUsername(username);
        admin.setDisplayName("同鹤汇管理员");
        admin.setPassword(passwords.encode(password));
        admin.setRole(Role.ADMIN);
        users.save(admin);
    }
}
