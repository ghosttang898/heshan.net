package net.tonghehui.backend.admin;

import org.springframework.data.jpa.repository.JpaRepository;

public interface FounderIdentityRepository extends JpaRepository<FounderIdentity, Long> {
    boolean existsByUserId(Long userId);
}
