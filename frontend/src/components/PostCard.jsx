import { Link } from "react-router-dom";

export default function PostCard({ post }) {
  const createdAt = post.createdAt
    ? new Date(post.createdAt).toLocaleString()
    : "Unknown time";

  return (
    <article className="card post-card">
      <div className="post-meta">
        <span>{post.type}</span>
        <span> · </span>
        <span>{createdAt}</span>
      </div>
      <h2>{post.title}</h2>
      <p className="post-content">{post.content}</p>
      <Link to={`/posts/${post.id}`}>查看详情</Link>
    </article>
  );
}
