import { formatUserName } from "../userName";

export default function CommentList({ comments }) {
  if (comments.length === 0) {
    return <p className="muted">还没有评论。</p>;
  }

  return (
    <div className="comment-list">
      {comments.map((comment) => (
        <article key={comment.id} className="comment-item">
          <div className="comment-meta">
            <strong>{formatUserName(comment.displayName, comment.username)}</strong>
            <span> · </span>
            <span>{new Date(comment.createdAt).toLocaleString()}</span>
          </div>
          <p className="post-content">{comment.content}</p>
        </article>
      ))}
    </div>
  );
}
