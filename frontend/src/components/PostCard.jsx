import { Link } from "react-router-dom";
import PostReplies from "./PostReplies";
import { formatUserName } from "../userName";

export default function PostCard({ post }) {
  const createdAt = post.createdAt
    ? new Date(post.createdAt).toLocaleString()
    : "Unknown time";

  return (
    <article className="card post-card">
      <div className="post-meta">
        <span>发表人: {formatUserName(
          post.authorDisplayName,
          post.authorUsername,
          "未记录",
        )}</span>
        <span> · </span>
        <span>{post.type}</span>
        <span> · </span>
        <span>{createdAt}</span>
      </div>
      <h2>{post.title}</h2>
      <p className="post-content">{post.content}</p>
      <div className="post-actions">
        <Link to={`/posts/${post.id}`}>查看详情</Link>
      </div>
      <PostReplies postId={post.id} />
    </article>
  );
}
