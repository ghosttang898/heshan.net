package net.tonghehui.backend.admin;

import java.time.LocalDate;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import net.tonghehui.backend.comment.Comment;
import net.tonghehui.backend.comment.CommentRepository;
import net.tonghehui.backend.post.Post;
import net.tonghehui.backend.post.PostRepository;
import net.tonghehui.backend.post.PostType;
import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.user.UserRepository;
import net.tonghehui.backend.moderation.ContentStatus;
import net.tonghehui.backend.admin.AdminDtos.*;

@Service
@Transactional(readOnly = true)
public class AdminService {
    private final UserRepository users;
    private final PostRepository posts;
    private final CommentRepository comments;

    public AdminService(UserRepository users, PostRepository posts, CommentRepository comments) {
        this.users = users;
        this.posts = posts;
        this.comments = comments;
    }

    public Dashboard dashboard() {
        var start = LocalDate.now().atStartOfDay();
        var end = start.plusDays(1);
        return new Dashboard(users.count(), posts.count(), comments.count(),
                users.countByCreatedAtGreaterThanEqualAndCreatedAtLessThan(start, end),
                posts.countByCreatedAtGreaterThanEqualAndCreatedAtLessThan(start, end),
                comments.countByCreatedAtGreaterThanEqualAndCreatedAtLessThan(start, end),
                posts.findTop5ByOrderByCreatedAtDescIdDesc().stream().map(PostItem::from).toList(),
                userItems(users.findTop5ByOrderByCreatedAtDescIdDesc()));
    }

    public PageResult<PostItem> posts(int page, int size, String search, PostType type, ContentStatus status) {
        Specification<Post> spec = (root, query, cb) -> {
            var predicate = cb.conjunction();
            if (type != null) predicate = cb.and(predicate, cb.equal(root.get("type"), type));
            if (status != null) predicate = cb.and(predicate, cb.equal(root.get("status"), status));
            if (search != null && !search.isBlank()) {
                String pattern = pattern(search);
                predicate = cb.and(predicate, cb.or(
                        cb.like(cb.lower(root.get("title")), pattern, '\\'),
                        cb.like(cb.lower(root.get("content")), pattern, '\\')));
            }
            return predicate;
        };
        return PageResult.from(posts.findAll(spec, pageable(page, size)).map(PostItem::from));
    }

    public PostItem post(Long id) {
        return PostItem.from(findPost(id));
    }

    @Transactional
    public PostItem updatePostStatus(Long id, ContentStatus status) {
        requireStatus(status);
        Post post = findPost(id);
        post.setStatus(status);
        return PostItem.from(posts.save(post));
    }

    public PageResult<CommentItem> comments(int page, int size, String search, ContentStatus status) {
        Specification<Comment> spec = (root, query, cb) -> {
            var predicate = cb.conjunction();
            if (status != null) predicate = cb.and(predicate, cb.equal(root.get("status"), status));
            if (search != null && !search.isBlank()) {
                predicate = cb.and(predicate, cb.like(cb.lower(root.get("content")), pattern(search), '\\'));
            }
            return predicate;
        };
        return PageResult.from(comments.findAll(spec, pageable(page, size)).map(CommentItem::from));
    }

    public CommentItem comment(Long id) {
        return CommentItem.from(findComment(id));
    }

    @Transactional
    public CommentItem updateCommentStatus(Long id, ContentStatus status) {
        requireStatus(status);
        Comment comment = findComment(id);
        comment.setStatus(status);
        return CommentItem.from(comments.save(comment));
    }

    public PageResult<UserItem> users(int page, int size, String search, Role role) {
        return users(page, size, search, role, false);
    }

    public PageResult<UserItem> administrators(int page, int size, String search, Role role) {
        return users(page, size, search, role, true);
    }

    private PageResult<UserItem> users(int page, int size, String search, Role role, boolean administratorsOnly) {
        Specification<User> spec = (root, query, cb) -> {
            var predicate = cb.conjunction();
            if (administratorsOnly) predicate = cb.and(predicate, root.get("role").in(Role.ADMIN, Role.SUPER_ADMIN));
            if (role != null) predicate = cb.and(predicate, cb.equal(root.get("role"), role));
            if (search != null && !search.isBlank()) {
                String pattern = pattern(search);
                predicate = cb.and(predicate, cb.or(
                        cb.like(cb.lower(root.get("username")), pattern, '\\'),
                        cb.like(cb.lower(root.get("displayName")), pattern, '\\')));
            }
            return predicate;
        };
        var result = users.findAll(spec, pageable(page, size));
        return new PageResult<>(userItems(result.getContent()), result.getNumber(), result.getSize(),
                result.getTotalElements(), result.getTotalPages());
    }

    public UserItem user(Long id) {
        User user = users.findById(id).orElseThrow(() -> notFound("User"));
        return UserItem.from(user, posts.countByAuthorId(id), comments.countByUserId(id));
    }

    private List<UserItem> userItems(List<User> items) {
        if (items.isEmpty()) return List.of();
        List<Long> ids = items.stream().map(User::getId).toList();
        Map<Long, Long> postCounts = counts(posts.countForAuthors(ids));
        Map<Long, Long> commentCounts = counts(comments.countForAuthors(ids));
        return items.stream().map(user -> UserItem.from(user, postCounts.getOrDefault(user.getId(), 0L),
                commentCounts.getOrDefault(user.getId(), 0L))).toList();
    }

    private Map<Long, Long> counts(List<AuthorCount> counts) {
        return counts.stream().collect(Collectors.toMap(AuthorCount::getUserId, AuthorCount::getTotal));
    }

    private Post findPost(Long id) {
        return posts.findById(id).orElseThrow(() -> notFound("Post"));
    }

    private Comment findComment(Long id) {
        return comments.findById(id).orElseThrow(() -> notFound("Comment"));
    }

    private ResponseStatusException notFound(String entity) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, entity + " not found");
    }

    private void requireStatus(ContentStatus status) {
        if (status == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Status is required");
    }

    private PageRequest pageable(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Page must be nonnegative; size must be 1 to 100");
        }
        return PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt", "id"));
    }

    private String pattern(String search) {
        return "%" + search.trim().toLowerCase(Locale.ROOT).replace("\\", "\\\\")
                .replace("%", "\\%").replace("_", "\\_") + "%";
    }
}
