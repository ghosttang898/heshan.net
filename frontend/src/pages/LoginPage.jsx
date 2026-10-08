import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { login } from "../api";
import { saveAuth } from "../auth";
import SiteHeader from "../components/SiteHeader";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [formData, setFormData] = useState({
    username: "",
    password: "",
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
      const response = await login(formData);
      saveAuth(response.data);
      const destination = location.state?.from;
      navigate(destination?.startsWith("/admin") ? destination : "/chat", { replace: true });
    } catch (requestError) {
      setError("登录失败，请检查用户名和密码。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <div className="stack">
        <SiteHeader />
        <form className="card form-grid" onSubmit={handleSubmit}>
          <h1>登录</h1>
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
            {submitting ? "登录中..." : "登录"}
          </button>
          <p className="muted">
            没有账号？<Link to="/register">去注册</Link>
          </p>
        </form>
      </div>
    </main>
  );
}
