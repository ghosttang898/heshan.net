import { useEffect, useState } from "react";
import { createComment, getComments } from "../api";
import { getAuth, isAuthenticated, subscribeAuthChange } from "../auth";
import AddCommentForm from "./AddCommentForm";
import CommentList from "./CommentList";

export default function PostReplies({ postId }) {
  const [expanded, setExpanded] = useState(false);
  const [comments, setComments] = useState([]);
  const [status, setStatus] = useState("idle");
  const [auth, setAuth] = useState(getAuth());

  useEffect(() => subscribeAuthChange(() => setAuth(getAuth())), []);

  async function loadComments() {
    setStatus("loading");

    try {
      const response = await getComments(postId);
      setComments(response.data);
      setStatus("ready");
    } catch (error) {
      setStatus("error");
    }
  }

  async function handleToggle() {
    const nextExpanded = !expanded;
    setExpanded(nextExpanded);

    if (nextExpanded && status === "idle") {
      await loadComments();
    }
  }

  async function handleCreateComment(payload) {
    await createComment(postId, payload);
    await loadComments();
  }

  return (
    <section className="reply-panel">
      <button className="button button-secondary reply-toggle" type="button" onClick={handleToggle}>
        {expanded ? "收起回复" : `回复${comments.length ? ` (${comments.length})` : ""}`}
      </button>

      {expanded ? (
        <div className="reply-content">
          {status === "loading" ? <p className="muted">正在加载回复...</p> : null}
          {status === "error" ? <p className="error-text">回复加载失败，请稍后再试。</p> : null}
          {status === "ready" ? <CommentList comments={comments} /> : null}
          <AddCommentForm
            onSubmit={handleCreateComment}
            isAuthenticated={isAuthenticated()}
            displayName={auth?.displayName || "匿名用户"}
            username={auth?.username}
          />
        </div>
      ) : null}
    </section>
  );
}
