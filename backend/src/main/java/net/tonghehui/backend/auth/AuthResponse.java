package net.tonghehui.backend.auth;

import net.tonghehui.backend.user.Role;

public class AuthResponse {

    private final String token;
    private final String username;
    private final String displayName;
    private final Role role;

    public AuthResponse(String token, String username, String displayName, Role role) {
        this.token = token;
        this.username = username;
        this.displayName = displayName;
        this.role = role;
    }

    public String getToken() {
        return token;
    }

    public Role getRole() {
        return role;
    }

    public String getUsername() {
        return username;
    }

    public String getDisplayName() {
        return displayName;
    }
}
