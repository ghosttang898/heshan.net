package net.tonghehui.backend.geolocation;

import static org.assertj.core.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

// Opt-in real data smoke test; normal CI needs no licensed database or network.
@EnabledIfSystemProperty(named = "geoip.test.database", matches = ".+")
class LocalDatabaseTest {
    @Test void readsRealUsChinaAndIpv6Records() {
        var service = new IpGeolocationService(System.getProperty("geoip.test.database"), 1000);
        try {
            assertThat(service.locate("8.8.8.8").countryCode()).isEqualTo("US");
            assertThat(service.locate("114.114.114.114").countryCode()).isEqualTo("CN");
            var ipv6 = service.locate("2001:4860:4860::8888");
            assertThat(ipv6.status()).isEqualTo(IpLocationStatus.RESOLVED);
            assertThat(ipv6.countryCode()).matches("[A-Z]{2}");
        } finally { service.close(); }
    }
}
