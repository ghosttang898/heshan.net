package net.tonghehui.backend.admin;

import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.domain.Page;
import net.tonghehui.backend.moderation.ContentStatus;
import net.tonghehui.backend.post.Post;
import net.tonghehui.backend.post.PostType;
import net.tonghehui.backend.comment.Comment;
import net.tonghehui.backend.user.Role;
import net.tonghehui.backend.user.User;
import net.tonghehui.backend.geolocation.IpLocationStatus;

public final class AdminDtos {
    private AdminDtos() {}

    public record Author(Long id, String username, String displayName) {
        public static Author from(User user) {
            return user == null ? null : new Author(user.getId(), user.getUsername(), user.getDisplayName());
        }
    }

    public record PostItem(Long id, String title, String content, Author author, PostType type,
            ContentStatus status, LocalDateTime createdAt, String nickname, String location, String yearRange,
            String ipCountryCode, String ipCountry, String ipRegion, String ipCity, IpLocationStatus ipLocationStatus) {
        public static PostItem from(Post post) {
            return new PostItem(post.getId(), post.getTitle(), post.getContent(), Author.from(post.getAuthor()),
                    post.getType(), post.getStatus(), post.getCreatedAt(), post.getNickname(), post.getLocation(), post.getYearRange(),
                    post.getIpCountryCode(), post.getIpCountry(), post.getIpRegion(), post.getIpCity(), post.getIpLocationStatus());
        }
    }

    public record CommentItem(Long id, String content, Author author, Long postId, String postTitle,
            ContentStatus status, LocalDateTime createdAt, String ipCountryCode, String ipCountry, String ipRegion,
            String ipCity, IpLocationStatus ipLocationStatus) {
        public static CommentItem from(Comment comment) {
            return new CommentItem(comment.getId(), comment.getContent(), Author.from(comment.getUser()),
                    comment.getPost().getId(), comment.getPost().getTitle(), comment.getStatus(), comment.getCreatedAt(),
                    comment.getIpCountryCode(), comment.getIpCountry(), comment.getIpRegion(), comment.getIpCity(), comment.getIpLocationStatus());
        }
    }

    public record UserItem(Long id, String username, String displayName, Role role, LocalDateTime createdAt,
            long postCount, long commentCount) {
        public static UserItem from(User user, long posts, long comments) {
            return new UserItem(user.getId(), user.getUsername(), user.getDisplayName(), user.getRole(),
                    user.getCreatedAt(), posts, comments);
        }
    }

    public record PageResult<T>(List<T> content, int page, int size, long totalElements, int totalPages) {
        public static <T> PageResult<T> from(Page<T> page) {
            return new PageResult<>(page.getContent(), page.getNumber(), page.getSize(), page.getTotalElements(), page.getTotalPages());
        }
    }

    public record StatusRequest(ContentStatus status) {}

    public record Dashboard(long totalUsers, long totalPosts, long totalComments, long todayNewUsers,
            long todayNewPosts, long todayNewComments, List<PostItem> recentPosts, List<UserItem> recentUsers) {}
}
