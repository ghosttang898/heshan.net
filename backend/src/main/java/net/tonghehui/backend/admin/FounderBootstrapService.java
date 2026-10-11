package net.tonghehui.backend.admin;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import javax.sql.DataSource;
import java.sql.SQLException;
import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FounderBootstrapService {
    private final DataSource dataSource;
    private final UserRepository users;
    private final FounderIdentityRepository founders;
    private final RoleChangeAuditRepository audits;
    @PersistenceContext private EntityManager entities;

    public FounderBootstrapService(DataSource dataSource, UserRepository users,
            FounderIdentityRepository founders, RoleChangeAuditRepository audits) {
        this.dataSource = dataSource;
        this.users = users;
        this.founders = founders;
        this.audits = audits;
    }

    @Transactional
    public void initialize(Long id, String username, Long confirmedId, String confirmedUsername) {
        // Check the actual connection, not an environment variable that might be overridden.
        try (var connection = dataSource.getConnection()) {
            String url = connection.getMetaData().getURL();
            if (!url.startsWith("jdbc:h2:file:") && !url.startsWith("jdbc:postgresql://")) {
                throw new IllegalStateException("Founder initialization requires persistent PostgreSQL or H2 file storage");
            }
        } catch (SQLException exception) {
            throw new IllegalStateException("Cannot verify persistent database", exception);
        }
        if (id == null || id <= 0 || !id.equals(confirmedId) || username == null || username.isBlank()
                || !username.equals(confirmedUsername)) {
            throw new IllegalArgumentException("Confirm both the owner user ID and exact username");
        }
        if (founders.existsById(1L) || users.existsByRole(Role.SUPER_ADMIN)) {
            throw new IllegalStateException("Founder initialization has already been completed; no second SUPER_ADMIN is allowed");
        }
        var target = users.findLockedById(id).orElseThrow(() -> new IllegalArgumentException("User ID does not exist"));
        if (!username.equals(target.getUsername())) throw new IllegalArgumentException("User ID and username do not match");
        Role oldRole = target.getRole();
        // Always INSERT: concurrent initialization must fail the singleton PK rather than overwrite its owner.
        entities.persist(new FounderIdentity(id));
        entities.flush();
        target.setRole(Role.SUPER_ADMIN);
        audits.save(new RoleChangeAudit(id, id, oldRole, Role.SUPER_ADMIN, RoleChangeAudit.Action.INITIALIZE_FOUNDER));
    }
}
