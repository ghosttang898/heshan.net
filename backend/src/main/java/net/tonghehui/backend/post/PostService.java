package net.tonghehui.backend.post;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;
import net.tonghehui.backend.moderation.ContentStatus;
import net.tonghehui.backend.geolocation.IpGeolocationService;

@Service
public class PostService {

    private final PostRepository postRepository;
    private final UserRepository userRepository;
    private final IpGeolocationService geolocation;

    public PostService(PostRepository postRepository, UserRepository userRepository, IpGeolocationService geolocation) {
        this.postRepository = postRepository;
        this.userRepository = userRepository;
        this.geolocation = geolocation;
    }

    public List<Post> findAll() {
        return postRepository.findAllByStatusOrderByCreatedAtDesc(ContentStatus.PUBLISHED);
    }

    public Post findById(Long id) {
        return postRepository.findByIdAndStatus(id, ContentStatus.PUBLISHED)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Post not found"));
    }

    public Post create(Post post, String username, String clientIp) {
        User author = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "User not found"));

        post.setId(null);
        post.setStatus(ContentStatus.PUBLISHED);
        post.setCreatedAt(null);
        post.setNickname(normalize(post.getNickname()));
        post.setLocation(normalize(post.getLocation()));
        post.setYearRange(normalize(post.getYearRange()));
        post.setAuthor(author);
        post.setIpLocation(geolocation.locate(clientIp));
        return postRepository.save(post);
    }

    private String normalize(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
