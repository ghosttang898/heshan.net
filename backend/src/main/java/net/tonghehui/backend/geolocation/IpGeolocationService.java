package net.tonghehui.backend.geolocation;

import java.io.File;
import java.io.IOException;
import java.net.InetAddress;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import com.maxmind.db.Reader.FileMode;
import com.maxmind.geoip2.DatabaseReader;
import com.maxmind.geoip2.exception.AddressNotFoundException;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class IpGeolocationService {
    private static final Logger LOG = LoggerFactory.getLogger(IpGeolocationService.class);
    private final DatabaseReader reader;
    private final long timeoutMs;
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(16), task -> {
                Thread thread = new Thread(task, "ip-geolocation"); thread.setDaemon(true); return thread;
            }, new ThreadPoolExecutor.AbortPolicy());

    @Autowired
    public IpGeolocationService(@Value("${app.geolocation.database-path:}") String path,
            @Value("${app.geolocation.timeout-ms:200}") long timeoutMs) {
        this(openDatabase(path), timeoutMs);
    }

    IpGeolocationService(DatabaseReader reader, long timeoutMs) {
        this.reader = reader;
        this.timeoutMs = Math.max(1, Math.min(timeoutMs, 1000));
    }

    private static DatabaseReader openDatabase(String path) {
        DatabaseReader loaded = null;
        if (!path.isBlank()) {
            try {
                loaded = new DatabaseReader.Builder(new File(path)).fileMode(FileMode.MEMORY)
                        .locales(List.of("zh-CN", "en")).build();
            } catch (IOException | RuntimeException exception) {
                LOG.warn("IP location database unavailable; publishing will continue without location");
            }
        }
        return loaded;
    }

    public IpLocation locate(String clientIp) {
        InetAddress address = IpAddresses.parse(clientIp);
        if (address == null) return IpLocation.unknown(IpLocationStatus.INVALID_IP);
        if (!IpAddresses.isPublic(address)) return IpLocation.unknown(IpLocationStatus.NON_PUBLIC);
        if (reader == null) return IpLocation.unknown(IpLocationStatus.DATABASE_UNAVAILABLE);
        Future<IpLocation> task;
        try { task = worker.submit(() -> lookup(address)); }
        catch (RejectedExecutionException exception) { return IpLocation.unknown(IpLocationStatus.TIMEOUT); }
        try { return task.get(timeoutMs, TimeUnit.MILLISECONDS); }
        catch (TimeoutException exception) {
            task.cancel(true); worker.purge(); return IpLocation.unknown(IpLocationStatus.TIMEOUT);
        } catch (InterruptedException exception) {
            task.cancel(true); Thread.currentThread().interrupt(); return IpLocation.unknown(IpLocationStatus.LOOKUP_FAILED);
        } catch (ExecutionException exception) { return IpLocation.unknown(IpLocationStatus.LOOKUP_FAILED); }
    }

    private IpLocation lookup(InetAddress address) throws Exception {
        try {
            var result = reader.city(address);
            String code = result.country().isoCode();
            if (code == null || code.isBlank()) return IpLocation.unknown(IpLocationStatus.NOT_FOUND);
            String country = new Locale("", code).getDisplayCountry(Locale.SIMPLIFIED_CHINESE);
            return new IpLocation(code, country, result.mostSpecificSubdivision().name(),
                    result.city().name(), IpLocationStatus.RESOLVED);
        } catch (AddressNotFoundException exception) { return IpLocation.unknown(IpLocationStatus.NOT_FOUND); }
    }

    @PreDestroy
    public void close() {
        worker.shutdownNow();
        if (reader != null) {
            try { reader.close(); }
            catch (IOException exception) { LOG.warn("IP location database could not be closed"); }
        }
    }
}
