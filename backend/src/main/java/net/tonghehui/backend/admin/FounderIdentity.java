package net.tonghehui.backend.admin;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

@Entity
@Table(name = "founder_identity")
public class FounderIdentity {
    @Id
    private Long id;
    @Column(nullable = false, unique = true, updatable = false)
    private Long userId;
    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected FounderIdentity() {}

    public FounderIdentity(Long userId) {
        this.id = 1L;
        this.userId = userId;
        this.createdAt = LocalDateTime.now();
    }

    public Long getUserId() { return userId; }
}
