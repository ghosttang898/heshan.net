package net.tonghehui.backend.geolocation;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.io.IOException;
import java.net.InetAddress;
import java.util.List;
import java.util.Map;
import com.maxmind.geoip2.DatabaseReader;
import com.maxmind.geoip2.model.CityResponse;
import com.maxmind.geoip2.record.Country;
import com.maxmind.geoip2.record.City;
import com.maxmind.geoip2.record.Subdivision;
import org.junit.jupiter.api.Test;

class IpGeolocationServiceTest {
    private CityResponse response(String code, String region, String city) {
        return new CityResponse(new City(List.of("en"), null, null, Map.of("en", city)), null,
                new Country(List.of("en"), null, null, false, code, Map.of()), null, null, null, null, null,
                List.of(new Subdivision(List.of("en"), null, null, null, Map.of("en", region))), null);
    }

    @Test void resolvesUsChinaAndIpv6DatabaseResults() throws Exception {
        var reader = mock(DatabaseReader.class);
        when(reader.city(InetAddress.getByName("8.8.8.8"))).thenReturn(response("US", "Pennsylvania", "Philadelphia"));
        when(reader.city(InetAddress.getByName("114.114.114.114"))).thenReturn(response("CN", "Guangdong", "Jiangmen"));
        when(reader.city(InetAddress.getByName("2001:4860:4860::8888"))).thenReturn(response("US", "California", "Mountain View"));
        var service = new IpGeolocationService(reader, 1000);
        try {
            assertThat(service.locate("8.8.8.8")).isEqualTo(new IpLocation("US", "美国", "Pennsylvania", "Philadelphia", IpLocationStatus.RESOLVED));
            assertThat(service.locate("114.114.114.114").country()).isEqualTo("中国");
            assertThat(service.locate("2001:4860:4860::8888").status()).isEqualTo(IpLocationStatus.RESOLVED);
            assertThat(service.locate("127.0.0.1").status()).isEqualTo(IpLocationStatus.NON_PUBLIC);
            assertThat(service.locate("localhost").status()).isEqualTo(IpLocationStatus.INVALID_IP);
            verify(reader, times(3)).city(any());
        } finally { service.close(); }
    }

    @Test void missingOrCorruptDatabaseDegradesGracefully() {
        var service = new IpGeolocationService("/missing/location.mmdb", 200);
        try { assertThat(service.locate("8.8.8.8").status()).isEqualTo(IpLocationStatus.DATABASE_UNAVAILABLE); }
        finally { service.close(); }
    }

    @Test void failuresAndTimeoutsAreBoundedAndDoNotLeakResults() throws Exception {
        var reader = mock(DatabaseReader.class);
        when(reader.city(any())).thenThrow(new IOException("test failure"));
        var service = new IpGeolocationService(reader, 30);
        try { assertThat(service.locate("8.8.8.8").status()).isEqualTo(IpLocationStatus.LOOKUP_FAILED); }
        finally { service.close(); }
        var slowReader = mock(DatabaseReader.class);
        when(slowReader.city(any())).thenAnswer(invocation -> { Thread.sleep(5000); return response("US", "Test", "Test"); });
        var slow = new IpGeolocationService(slowReader, 30);
        long start = System.nanoTime();
        try {
            assertThat(slow.locate("8.8.8.8").status()).isEqualTo(IpLocationStatus.TIMEOUT);
            assertThat((System.nanoTime() - start) / 1_000_000).isLessThan(1000);
        } finally { slow.close(); }
    }
}
