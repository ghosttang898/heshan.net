package net.tonghehui.backend.geolocation;

import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.web.util.matcher.IpAddressMatcher;
import org.springframework.stereotype.Component;

@Component
public class ClientIpResolver {
    private final List<IpAddressMatcher> trustedProxies;

    public ClientIpResolver(@Value("${app.geolocation.trusted-proxies:}") String configured) {
        trustedProxies = new ArrayList<>();
        for (String cidr : configured.split(",")) {
            if (cidr.isBlank()) continue;
            String[] parts = cidr.trim().split("/", -1);
            InetAddress address = IpAddresses.parse(parts[0]);
            if (address == null || parts.length > 2) throw new IllegalArgumentException("Invalid trusted proxy CIDR");
            if (parts.length == 2) {
                int prefix = Integer.parseInt(parts[1]);
                if (prefix <= 0 || prefix > address.getAddress().length * 8) {
                    throw new IllegalArgumentException("Trusted proxy CIDR must not trust all addresses");
                }
            }
            trustedProxies.add(new IpAddressMatcher(cidr.trim()));
        }
    }

    public String resolve(HttpServletRequest request) {
        InetAddress peer = IpAddresses.parse(request.getRemoteAddr());
        if (peer == null) return null;
        String current = peer.getHostAddress();
        if (!trusted(current)) return current;
        var headers = request.getHeaders("X-Forwarded-For");
        if (headers == null || !headers.hasMoreElements()) return current;
        String header = headers.nextElement();
        if (headers.hasMoreElements() || header.length() > 1024) return null;
        String[] chain = header.split(",", -1);
        if (chain.length > 20) return null;
        List<String> addresses = new ArrayList<>();
        for (String part : chain) {
            InetAddress address = IpAddresses.parse(part);
            if (address == null) return null;
            addresses.add(address.getHostAddress());
        }
        // Walk from the socket peer towards the client. Stop at the first untrusted hop.
        for (int i = addresses.size() - 1; i >= 0 && trusted(current); i--) current = addresses.get(i);
        return current;
    }

    private boolean trusted(String address) {
        return trustedProxies.stream().anyMatch(proxy -> proxy.matches(address));
    }
}
