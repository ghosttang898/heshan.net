import PostCard from "./PostCard";

export default function PostList({ posts, emptyText, loading = false }) {
  if (loading) {
    return <section className="card"><p className="muted" role="status">正在加载帖子...</p></section>;
  }

  if (posts.length === 0) {
    return (
      <section className="card">
        <p className="muted">{emptyText}</p>
      </section>
    );
  }

  return (
    <section className="post-list">
      {posts.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}
    </section>
  );
}
