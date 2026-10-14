import { useState } from "react";

import { validatePost, submissionError } from "../formValidation";

const initialForm = {
  title: "",
  content: "",
  type: "FIND_PERSON",
  nickname: "",
  location: "",
  yearRange: "",
};

export default function CreateFindPersonPostForm({ onSubmit }) {
  const [formData, setFormData] = useState(initialForm);
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
      setFormData(initialForm);
    } catch (requestError) {
      setError(submissionError(requestError, "发布失败，请稍后重试。"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card form-grid" onSubmit={handleSubmit}>
      <h2>发布寻人帖子</h2>
      <label className="field">
        <span>标题</span>
        <input name="title" maxLength={255} value={formData.title} onChange={handleChange} required />
      </label>
      <label className="field">
        <span>昵称 / 旧用户名</span>
        <input
          name="nickname"
          maxLength={255}
          value={formData.nickname}
          onChange={handleChange}
          placeholder="例如：阿强"
        />
      </label>
      <label className="field">
        <span>地点</span>
        <input
          name="location"
          maxLength={255}
          value={formData.location}
          onChange={handleChange}
          placeholder="例如：鹤山，沙坪"
        />
      </label>
      <label className="field">
        <span>年份范围</span>
        <input
          name="yearRange"
          maxLength={255}
          value={formData.yearRange}
          onChange={handleChange}
          placeholder="例如：1999-2003"
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
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "提交中..." : "创建帖子"}
      </button>
    </form>
  );
}
