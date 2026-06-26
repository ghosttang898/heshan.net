package net.tonghehui.backend.auth;

import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import net.tonghehui.backend.security.JwtService;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuthenticationManager authenticationManager;
    private final JwtService jwtService;

    public AuthService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            AuthenticationManager authenticationManager,
            JwtService jwtService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.authenticationManager = authenticationManager;
        this.jwtService = jwtService;
    }

    public AuthResponse register(RegisterRequest request) {
        if (request.getUsername() == null || request.getPassword() == null || request.getDisplayName() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Missing required fields");
        }

        String username = request.getUsername().trim();
        String displayName = request.getDisplayName().trim();

        if (username.isEmpty() || request.getPassword().isBlank() || displayName.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Missing required fields");
        }

        if (userRepository.existsByUsername(username)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Username already exists");
        }

        User user = new User();
        user.setUsername(username);
        user.setPassword(passwordEncoder.encode(request.getPassword()));
        user.setDisplayName(displayName);

        User savedUser = userRepository.save(user);
        String token = jwtService.generateToken(savedUser.getUsername());
        return new AuthResponse(token, savedUser.getUsername(), savedUser.getDisplayName());
    }

    public AuthResponse login(LoginRequest request) {
        if (request.getUsername() == null || request.getPassword() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Missing required fields");
        }

        String username = request.getUsername().trim();

        if (username.isEmpty() || request.getPassword().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Missing required fields");
        }

        authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(username, request.getPassword()));

        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid credentials"));

        String token = jwtService.generateToken(user.getUsername());
        return new AuthResponse(token, user.getUsername(), user.getDisplayName());
    }
}
