package net.tonghehui.backend.common;

import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class InputValidation {
    private InputValidation() {}

    public static void text(String value, String field, int limit, boolean required) {
        if (required && (value == null || value.isBlank())) {
            reject(field + " is required");
        }
        if (value != null && value.codePointCount(0, value.length()) > limit) {
            reject(field + " is too long");
        }
    }

    public static void password(String value) {
        text(value, "Password", 72, true);
        // BCrypt limits bytes, not characters; never silently truncate a password.
        if (value.getBytes(StandardCharsets.UTF_8).length > 72) {
            reject("Password exceeds 72 UTF-8 bytes");
        }
    }

    private static void reject(String reason) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
