package net.tonghehui.backend.geolocation;

import static org.assertj.core.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class ClientIpResolverTest {
    private MockHttpServletRequest request(String peer, String chain) {
        var request = new MockHttpServletRequest(); request.setRemoteAddr(peer);
        if (chain != null) request.addHeader("X-Forwarded-For", chain);
        request.addHeader("CF-Connecting-IP", "1.1.1.1");
        request.addHeader("Forwarded", "for=1.1.1.1");
        return request;
    }

    @Test void ignoresAllForwardingFromUntrustedPeers() {
        assertThat(new ClientIpResolver("").resolve(request("8.8.8.8", "1.1.1.1"))).isEqualTo("8.8.8.8");
        assertThat(new ClientIpResolver("10.0.0.0/24").resolve(request("127.0.0.1", "1.1.1.1"))).isEqualTo("127.0.0.1");
    }

    @Test void walksFromRightAndStopsAtFirstUntrustedHop() {
        var resolver = new ClientIpResolver("10.0.0.0/24,::1/128");
        assertThat(resolver.resolve(request("10.0.0.2", "1.1.1.1, 8.8.8.8, 10.0.0.3"))).isEqualTo("8.8.8.8");
        assertThat(resolver.resolve(request("::1", "2001:4860:4860::8888")))
                .isEqualTo(IpAddresses.parse("2001:4860:4860::8888").getHostAddress());
    }

    @Test void rejectsMalformedAmbiguousAndOverlongHeaders() {
        var resolver = new ClientIpResolver("10.0.0.2");
        for (String header : new String[]{"localhost", "1.1.1.1,", "[::1]:80", "fe80::1%eth0", "1.1.1.1,".repeat(200)}) {
            assertThat(resolver.resolve(request("10.0.0.2", header))).isNull();
        }
        var duplicate = request("10.0.0.2", "8.8.8.8"); duplicate.addHeader("X-Forwarded-For", "1.1.1.1");
        assertThat(resolver.resolve(duplicate)).isNull();
        assertThatThrownBy(() -> new ClientIpResolver("0.0.0.0/0")).isInstanceOf(IllegalArgumentException.class);
    }

    @Test void parsesLiteralsWithoutDnsAndClassifiesSpecialRanges() {
        for (String literal : new String[]{"localhost", "example.com", "127.1", "012.0.0.1", "1.2.3.999", "8.8.8.8:80"}) {
            assertThat(IpAddresses.parse(literal)).isNull();
        }
        for (String literal : new String[]{"127.0.0.1", "10.0.0.1", "100.64.1.1", "169.254.1.1", "192.168.1.1", "::1", "fc00::1", "fe80::1", "2001:db8::1", "::ffff:192.168.1.1", "224.0.0.1"}) {
            assertThat(IpAddresses.isPublic(IpAddresses.parse(literal))).as(literal).isFalse();
        }
        assertThat(IpAddresses.isPublic(IpAddresses.parse("8.8.8.8"))).isTrue();
        assertThat(IpAddresses.isPublic(IpAddresses.parse("2001:4860:4860::8888"))).isTrue();
    }
}
