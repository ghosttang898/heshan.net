import { useState } from "react";

import { validatePost, submissionError } from "../formValidation";

const initialForm = {
  title: "",
  content: "",
  type: "CHAT",
};

export default function CreatePostForm({ defaultType, onSubmit }) {
  const [formData, setFormData] = useState({
    ...initialForm,
    type: defaultType,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function handleChange(event) {
    const { name, value } = event.target;
    setFormData((current) => ({
      ...current,
      [name]: value,
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validatePost(formData);
    setError(validationError);
    if (validationError) return;
    setSubmitting(true);

    try {
      await onSubmit(formData);
      setFormData({
        ...initialForm,
        type: defaultType,
      });
    } catch (requestError) {
      setError(submissionError(requestError, "发布失败，请稍后重试。"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card form-grid" onSubmit={handleSubmit}>
      <h2>发布帖子</h2>
      <label className="field">
        <span>标题</span>
        <input
          name="title"
          maxLength={255}
          value={formData.title}
          onChange={handleChange}
          required
        />
      </label>
      <label className="field">
        <span>内容</span>
        <textarea
          name="content"
          maxLength={4000}
          value={formData.content}
          onChange={handleChange}
          required
        />
      </label>
      <label className="field">
        <span>类型</span>
        <select name="type" value={formData.type} onChange={handleChange}>
          <option value="CHAT">CHAT</option>
          <option value="FIND_PERSON">FIND_PERSON</option>
        </select>
      </label>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "提交中..." : "创建帖子"}
      </button>
    </form>
  );
}
