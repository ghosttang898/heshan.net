package net.tonghehui.backend.admin;

import org.springframework.data.jpa.repository.JpaRepository;

public interface RoleChangeAuditRepository extends JpaRepository<RoleChangeAudit, Long> {}
