package net.tonghehui.backend.geolocation;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;
import org.springframework.security.web.util.matcher.IpAddressMatcher;

final class IpAddresses {
    private IpAddresses() {}
    private static final List<IpAddressMatcher> SPECIAL_V4 = List.of(
            "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
            "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
            "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/3")
            .stream().map(IpAddressMatcher::new).toList();
    private static final List<IpAddressMatcher> SPECIAL_V6 = List.of(
            "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20")
            .stream().map(IpAddressMatcher::new).toList();

    static InetAddress parse(String literal) {
        if (literal == null || literal.length() > 45) return null;
        String value = literal.trim();
        // Only numeric literals reach InetAddress: no DNS, ports, zones, or hostnames.
        if (value.contains(":")) {
            if (!value.matches("[0-9a-fA-F:.]+")) return null;
        } else {
            String[] parts = value.split("\\.", -1);
            if (parts.length != 4) return null;
            for (String part : parts) {
                if (!part.matches("0|[1-9][0-9]{0,2}") || Integer.parseInt(part) > 255) return null;
            }
        }
        try { return InetAddress.getByName(value); }
        catch (UnknownHostException exception) { return null; }
    }

    static boolean isPublic(InetAddress address) {
        String ip = address.getHostAddress();
        if (address.getAddress().length == 4) return SPECIAL_V4.stream().noneMatch(cidr -> cidr.matches(ip));
        return new IpAddressMatcher("2000::/3").matches(ip)
                && SPECIAL_V6.stream().noneMatch(cidr -> cidr.matches(ip));
    }
}
