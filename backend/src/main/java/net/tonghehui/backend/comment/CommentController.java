package net.tonghehui.backend.comment;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/posts/{postId}/comments")
public class CommentController {

    private final CommentService commentService;

    public CommentController(CommentService commentService) {
        this.commentService = commentService;
    }

    @GetMapping
    public List<CommentResponse> getComments(@PathVariable Long postId) {
        return commentService.findByPostId(postId);
    }

    @PostMapping
    public CommentResponse createComment(
            @PathVariable Long postId,
            @RequestBody CreateCommentRequest request,
            Authentication authentication) {
        String username = authentication != null ? authentication.getName() : null;
        return commentService.create(postId, request, username);
    }
}
