package net.tonghehui.backend.comment;

import java.util.List;
import java.time.LocalDateTime;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import net.tonghehui.backend.moderation.ContentStatus;
import net.tonghehui.backend.admin.AuthorCount;

public interface CommentRepository extends JpaRepository<Comment, Long>, JpaSpecificationExecutor<Comment> {

    List<Comment> findAllByPostIdOrderByCreatedAtAsc(Long postId);
    List<Comment> findAllByPostIdAndStatusOrderByCreatedAtAsc(Long postId, ContentStatus status);
    long countByCreatedAtGreaterThanEqualAndCreatedAtLessThan(LocalDateTime start, LocalDateTime end);
    long countByUserId(Long id);

    @Query("select c.user.id as userId, count(c) as total from Comment c where c.user.id in :ids group by c.user.id")
    List<AuthorCount> countForAuthors(List<Long> ids);
}
