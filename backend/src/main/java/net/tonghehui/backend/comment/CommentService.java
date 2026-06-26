package net.tonghehui.backend.comment;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import net.tonghehui.backend.post.Post;
import net.tonghehui.backend.post.PostService;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;

@Service
public class CommentService {

    private final CommentRepository commentRepository;
    private final PostService postService;
    private final UserRepository userRepository;

    public CommentService(CommentRepository commentRepository, PostService postService, UserRepository userRepository) {
        this.commentRepository = commentRepository;
        this.postService = postService;
        this.userRepository = userRepository;
    }

    public List<CommentResponse> findByPostId(Long postId) {
        postService.findById(postId);
        return commentRepository.findAllByPostIdOrderByCreatedAtAsc(postId).stream()
                .map(this::toResponse)
                .toList();
    }

    public CommentResponse create(Long postId, CreateCommentRequest request, String username) {
        if (request.getContent() == null || request.getContent().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Comment content is required");
        }

        Post post = postService.findById(postId);
        Comment comment = new Comment();
        comment.setContent(request.getContent().trim());
        comment.setPost(post);

        if (username != null && !username.isBlank()) {
            User user = userRepository.findByUsername(username)
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "User not found"));
            comment.setUser(user);
        }

        return toResponse(commentRepository.save(comment));
    }

    private CommentResponse toResponse(Comment comment) {
        User user = comment.getUser();
        return new CommentResponse(
                comment.getId(),
                comment.getContent(),
                comment.getCreatedAt(),
                user != null ? user.getId() : null,
                user != null ? user.getUsername() : null,
                user != null ? user.getDisplayName() : null);
    }
}
