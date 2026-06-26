import PostCard from "./PostCard";

export default function PostList({ posts, emptyText }) {
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
