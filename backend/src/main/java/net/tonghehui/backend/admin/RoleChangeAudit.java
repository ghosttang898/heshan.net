package net.tonghehui.backend.admin;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import net.tonghehui.backend.user.Role;

@Entity
@Table(name = "role_change_audit")
public class RoleChangeAudit {
    public enum Action { GRANT_ADMIN, REVOKE_ADMIN, INITIALIZE_FOUNDER }

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, updatable = false)
    private Long actorId;
    @Column(nullable = false, updatable = false)
    private Long targetUserId;
    @Enumerated(EnumType.STRING) @Column(nullable = false, updatable = false)
    private Role oldRole;
    @Enumerated(EnumType.STRING) @Column(nullable = false, updatable = false)
    private Role newRole;
    @Enumerated(EnumType.STRING) @Column(nullable = false, updatable = false)
    private Action action;
    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected RoleChangeAudit() {}

    public RoleChangeAudit(Long actorId, Long targetUserId, Role oldRole, Role newRole, Action action) {
        this.actorId = actorId;
        this.targetUserId = targetUserId;
        this.oldRole = oldRole;
        this.newRole = newRole;
        this.action = action;
        this.createdAt = LocalDateTime.now();
    }

    public Long getActorId() { return actorId; }
    public Long getTargetUserId() { return targetUserId; }
    public Role getOldRole() { return oldRole; }
    public Role getNewRole() { return newRole; }
    public Action getAction() { return action; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
