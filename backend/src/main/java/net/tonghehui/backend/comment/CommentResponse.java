package net.tonghehui.backend.comment;

import java.time.LocalDateTime;
import net.tonghehui.backend.geolocation.IpLocationStatus;

public class CommentResponse {

    private final Long id;
    private final String content;
    private final LocalDateTime createdAt;
    private final Long userId;
    private final String username;
    private final String displayName;
    private final String ipCountryCode;
    private final String ipCountry;
    private final String ipRegion;
    private final String ipCity;
    private final IpLocationStatus ipLocationStatus;

    public CommentResponse(Long id, String content, LocalDateTime createdAt, Long userId, String username, String displayName,
            String ipCountryCode, String ipCountry, String ipRegion, String ipCity, IpLocationStatus ipLocationStatus) {
        this.id = id;
        this.content = content;
        this.createdAt = createdAt;
        this.userId = userId;
        this.username = username;
        this.displayName = displayName;
        this.ipCountryCode = ipCountryCode;
        this.ipCountry = ipCountry;
        this.ipRegion = ipRegion;
        this.ipCity = ipCity;
        this.ipLocationStatus = ipLocationStatus;
    }

    public String getIpCountryCode() { return ipCountryCode; }
    public String getIpCountry() { return ipCountry; }
    public String getIpRegion() { return ipRegion; }
    public String getIpCity() { return ipCity; }
    public IpLocationStatus getIpLocationStatus() { return ipLocationStatus; }

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
