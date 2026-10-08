package net.tonghehui.backend.geolocation;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.Column;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class IpLocatedContent {
    @Column(length = 2)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String ipCountryCode;
    @Column(length = 128)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String ipCountry;
    @Column(length = 128)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String ipRegion;
    @Column(length = 128)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String ipCity;
    @Enumerated(EnumType.STRING)
    @Column(length = 32)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private IpLocationStatus ipLocationStatus;

    public String getIpCountryCode() { return ipCountryCode; }
    public String getIpCountry() { return ipCountry; }
    public String getIpRegion() { return ipRegion; }
    public String getIpCity() { return ipCity; }
    public IpLocationStatus getIpLocationStatus() {
        return ipLocationStatus == null ? IpLocationStatus.UNKNOWN : ipLocationStatus;
    }

    @JsonIgnore
    public void setIpLocation(IpLocation location) {
        ipCountryCode = limited(location.countryCode(), 2);
        ipCountry = limited(location.country(), 128);
        ipRegion = limited(location.region(), 128);
        ipCity = limited(location.city(), 128);
        ipLocationStatus = location.status();
    }

    private String limited(String value, int length) {
        if (value == null || value.isBlank()) return null;
        return value.substring(0, Math.min(value.length(), length));
    }
}
