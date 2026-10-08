package net.tonghehui.backend.post;

import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import net.tonghehui.backend.moderation.ContentStatus;
import net.tonghehui.backend.admin.AuthorCount;

public interface PostRepository extends JpaRepository<Post, Long>, JpaSpecificationExecutor<Post> {

    List<Post> findAllByOrderByCreatedAtDesc();
    List<Post> findAllByStatusOrderByCreatedAtDesc(ContentStatus status);
    Optional<Post> findByIdAndStatus(Long id, ContentStatus status);
    long countByCreatedAtGreaterThanEqualAndCreatedAtLessThan(LocalDateTime start, LocalDateTime end);
    long countByAuthorId(Long id);
    List<Post> findTop5ByOrderByCreatedAtDescIdDesc();

    @Query("select p.author.id as userId, count(p) as total from Post p where p.author.id in :ids group by p.author.id")
    List<AuthorCount> countForAuthors(List<Long> ids);
}
