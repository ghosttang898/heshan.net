import { useState } from "react";
import { formatUserName } from "../userName";
import { validateFields, submissionError } from "../formValidation";

export default function AddCommentForm({
  onSubmit,
  isAuthenticated,
  displayName,
  username,
}) {
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validateFields({ content }, [["content", "评论内容", 2000, true]]);
    setError(validationError);
    if (validationError) return;
    setSubmitting(true);

    try {
      await onSubmit({ content });
      setContent("");
    } catch (requestError) {
      setError(submissionError(requestError, "评论失败，请稍后重试。"));
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
          maxLength={2000}
          value={content}
          onChange={(event) => setContent(event.target.value)}
          required
        />
      </label>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "提交中..." : "发表评论"}
      </button>
    </form>
  );
}
