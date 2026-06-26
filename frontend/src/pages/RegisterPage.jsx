import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { register } from "../api";
import { saveAuth } from "../auth";

export default function RegisterPage() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    username: "",
    password: "",
    displayName: "",
  });
  const [error, setError] = useState("");
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
    setError("");

    try {
      const response = await register(formData);
      saveAuth(response.data);
      navigate("/chat");
    } catch (requestError) {
      setError("注册失败，用户名可能已存在。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <form className="card form-grid" onSubmit={handleSubmit}>
        <h1>注册</h1>
        <label className="field">
          <span>用户名</span>
          <input
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
          />
        </label>
        <label className="field">
          <span>显示名</span>
          <input
            name="displayName"
            value={formData.displayName}
            onChange={handleChange}
            required
          />
        </label>
        <label className="field">
          <span>密码</span>
          <input
            type="password"
            name="password"
            value={formData.password}
            onChange={handleChange}
            required
          />
        </label>
        {error ? <p className="error-text">{error}</p> : null}
        <button className="button" type="submit" disabled={submitting}>
          {submitting ? "注册中..." : "注册"}
        </button>
        <p className="muted">
          已有账号？<Link to="/login">去登录</Link>
        </p>
      </form>
    </main>
  );
}
