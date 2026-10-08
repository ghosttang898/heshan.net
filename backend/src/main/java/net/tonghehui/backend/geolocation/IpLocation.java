package net.tonghehui.backend.geolocation;

public record IpLocation(String countryCode, String country, String region, String city, IpLocationStatus status) {
    public static IpLocation unknown(IpLocationStatus status) {
        return new IpLocation(null, null, null, null, status);
    }
}
