package net.tonghehui.backend.comment;

import java.time.LocalDateTime;

public class CommentResponse {

    private final Long id;
    private final String content;
    private final LocalDateTime createdAt;
    private final Long userId;
    private final String username;
    private final String displayName;

    public CommentResponse(Long id, String content, LocalDateTime createdAt, Long userId, String username, String displayName) {
        this.id = id;
        this.content = content;
        this.createdAt = createdAt;
        this.userId = userId;
        this.username = username;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getContent() {
        return content;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Long getUserId() {
        return userId;
    }

    public String getUsername() {
        return username;
    }

    public String getDisplayName() {
        return displayName;
    }
}
