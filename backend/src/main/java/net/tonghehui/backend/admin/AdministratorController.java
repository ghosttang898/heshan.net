package net.tonghehui.backend.admin;

import net.tonghehui.backend.user.Role;
import org.springframework.security.core.Authentication;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin")
@PreAuthorize("hasRole('SUPER_ADMIN')")
public class AdministratorController {
    public record RoleRequest(Role role, Role expectedRole) {}
    private final AdminService admin;
    private final AdministratorService administrators;

    public AdministratorController(AdminService admin, AdministratorService administrators) {
        this.admin = admin;
        this.administrators = administrators;
    }

    @GetMapping("/administrators")
    public AdminDtos.PageResult<AdminDtos.UserItem> list(
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String search, @RequestParam(required = false) Role role) {
        return admin.administrators(page, size, search, role);
    }

    @PatchMapping("/users/{id}/role")
    public AdminDtos.UserItem changeRole(@PathVariable Long id, @RequestBody RoleRequest request, Authentication authentication) {
        administrators.changeRole(authentication.getName(), id, request.role(), request.expectedRole());
        return admin.user(id);
    }
}
