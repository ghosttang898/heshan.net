package net.tonghehui.backend.post;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.servlet.http.HttpServletRequest;
import net.tonghehui.backend.geolocation.ClientIpResolver;

@RestController
@RequestMapping("/api/posts")
public class PostController {

    private final PostService postService;
    private final ClientIpResolver clientIps;

    public PostController(PostService postService, ClientIpResolver clientIps) {
        this.postService = postService;
        this.clientIps = clientIps;
    }

    @GetMapping
    public List<Post> getPosts() {
        return postService.findAll();
    }

    @GetMapping("/{id}")
    public Post getPost(@PathVariable Long id) {
        return postService.findById(id);
    }

    @PostMapping
    public Post createPost(@RequestBody Post post, Authentication authentication, HttpServletRequest request) {
        return postService.create(post, authentication.getName(), clientIps.resolve(request));
    }
}
