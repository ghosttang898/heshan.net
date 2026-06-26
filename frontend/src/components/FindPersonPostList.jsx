import { Link } from "react-router-dom";

export default function FindPersonPostList({ posts, emptyText }) {
  if (posts.length === 0) {
    return (
      <section className="card">
        <p className="muted">{emptyText}</p>
      </section>
    );
  }

  return (
    <section className="post-list">
      {posts.map((post) => {
        const createdAt = post.createdAt
          ? new Date(post.createdAt).toLocaleString()
          : "Unknown time";

        return (
          <article key={post.id} className="card post-card">
            <div className="post-meta">
              <span>{post.type}</span>
              <span> · </span>
              <span>{createdAt}</span>
            </div>
            <h2>{post.title}</h2>
            <div className="post-tags">
              {post.nickname ? <span className="tag">昵称: {post.nickname}</span> : null}
              {post.location ? <span className="tag">地点: {post.location}</span> : null}
              {post.yearRange ? <span className="tag">年份: {post.yearRange}</span> : null}
            </div>
            <p className="post-content">{post.content}</p>
            <Link to={`/posts/${post.id}`}>查看详情</Link>
          </article>
        );
      })}
    </section>
  );
}
