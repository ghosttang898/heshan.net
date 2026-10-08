package net.tonghehui.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TongHeHuiApplication {

    public static void main(String[] args) {
        if (java.util.Arrays.asList(args).contains("--initialize-founder")) {
            net.tonghehui.backend.admin.FounderBootstrapCommand.run(args);
            return;
        }
        SpringApplication.run(TongHeHuiApplication.class, args);
    }
}
