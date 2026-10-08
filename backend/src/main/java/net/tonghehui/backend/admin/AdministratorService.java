package net.tonghehui.backend.admin;

import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.UserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AdministratorService {
    private final UserRepository users;
    private final FounderIdentityRepository founders;
    private final RoleChangeAuditRepository audits;

    public AdministratorService(UserRepository users, FounderIdentityRepository founders, RoleChangeAuditRepository audits) {
        this.users = users;
        this.founders = founders;
        this.audits = audits;
    }

    @Transactional
    @PreAuthorize("hasRole('SUPER_ADMIN')")
    public void changeRole(String actorUsername, Long targetId, Role role, Role expectedRole) {
        if (role == null || expectedRole == null || role == Role.SUPER_ADMIN) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Only USER and ADMIN are accepted; expectedRole is required");
        }
        var actor = users.findByUsername(actorUsername)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN));
        if (actor.getRole() != Role.SUPER_ADMIN) throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        var target = users.findLockedById(targetId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        if (target.getRole() == Role.SUPER_ADMIN || founders.existsByUserId(targetId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Protected account");
        }
        if (target.getRole() != expectedRole || target.getRole() == role) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Role changed; refresh before confirming");
        }
        Role oldRole = target.getRole();
        target.setRole(role);
        audits.save(new RoleChangeAudit(actor.getId(), targetId, oldRole, role,
                role == Role.ADMIN ? RoleChangeAudit.Action.GRANT_ADMIN : RoleChangeAudit.Action.REVOKE_ADMIN));
    }
}
