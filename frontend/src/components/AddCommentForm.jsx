import { useState } from "react";
import { formatUserName } from "../userName";

export default function AddCommentForm({
  onSubmit,
  isAuthenticated,
  displayName,
  username,
}) {
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);

    try {
      await onSubmit({ content });
      setContent("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={handleSubmit}>
      <p className="muted">
        {isAuthenticated
          ? `当前身份: ${formatUserName(displayName, username)}`
          : "当前身份: 匿名用户"}
      </p>
      <label className="field">
        <span>评论内容</span>
        <textarea
          name="content"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          required
        />
      </label>
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "提交中..." : "发表评论"}
      </button>
    </form>
  );
}
