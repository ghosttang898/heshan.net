package net.tonghehui.backend.admin;

import org.springframework.web.bind.annotation.*;
import net.tonghehui.backend.admin.AdminDtos.*;
import net.tonghehui.backend.moderation.ContentStatus;
import net.tonghehui.backend.post.PostType;
import net.tonghehui.backend.user.Role;

@RestController
@RequestMapping("/api/admin")
public class AdminController {
    private final AdminService service;

    public AdminController(AdminService service) {
        this.service = service;
    }

    @GetMapping("/dashboard")
    public Dashboard dashboard() {
        return service.dashboard();
    }

    @GetMapping("/posts")
    public PageResult<PostItem> posts(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size, @RequestParam(required = false) String search,
            @RequestParam(required = false) PostType type, @RequestParam(required = false) ContentStatus status) {
        return service.posts(page, size, search, type, status);
    }

    @GetMapping("/posts/{id}")
    public PostItem post(@PathVariable Long id) {
        return service.post(id);
    }

    @PatchMapping("/posts/{id}/status")
    public PostItem postStatus(@PathVariable Long id, @RequestBody StatusRequest request) {
        return service.updatePostStatus(id, request.status());
    }

    @GetMapping("/comments")
    public PageResult<CommentItem> comments(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size, @RequestParam(required = false) String search,
            @RequestParam(required = false) ContentStatus status) {
        return service.comments(page, size, search, status);
    }

    @GetMapping("/comments/{id}")
    public CommentItem comment(@PathVariable Long id) {
        return service.comment(id);
    }

    @PatchMapping("/comments/{id}/status")
    public CommentItem commentStatus(@PathVariable Long id, @RequestBody StatusRequest request) {
        return service.updateCommentStatus(id, request.status());
    }

    @GetMapping("/users")
    public PageResult<UserItem> users(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size, @RequestParam(required = false) String search,
            @RequestParam(required = false) Role role) {
        return service.users(page, size, search, role);
    }

    @GetMapping("/users/{id}")
    public UserItem user(@PathVariable Long id) {
        return service.user(id);
    }
}
