import { useState } from "react";

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

  function handleChange(event) {
    const { name, value } = event.target;
    setFormData((current) => ({
      ...current,
      [name]: value,
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);

    try {
      await onSubmit(formData);
      setFormData({
        ...initialForm,
        type: defaultType,
      });
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
          value={formData.title}
          onChange={handleChange}
          required
        />
      </label>
      <label className="field">
        <span>内容</span>
        <textarea
          name="content"
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
      <button className="button" type="submit" disabled={submitting}>
        {submitting ? "提交中..." : "创建帖子"}
      </button>
    </form>
  );
}
