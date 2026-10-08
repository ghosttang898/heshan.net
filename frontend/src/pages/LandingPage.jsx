import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getHealth } from "../api";
import { clearAuth, getAuth, subscribeAuthChange } from "../auth";
import logoLockup from "../assets/logo-heshan-lockup.png";
import AdminLink from "../components/AdminLink";

export default function LandingPage() {
  const [health, setHealth] = useState("loading");
  const [auth, setAuth] = useState(getAuth());

  useEffect(() => {
    async function loadHealth() {
      try {
        const response = await getHealth();
        setHealth(response.data.status || "unknown");
      } catch (error) {
        setHealth("error");
      }
    }

    loadHealth();
  }, []);

  useEffect(() => subscribeAuthChange(() => setAuth(getAuth())), []);

  return (
    <main className="page landing-page">
      <section className="landing-shell">
        <nav className="site-nav">
          <Link className="brand-mark" to="/">
            <img src={logoLockup} alt="同鹤汇 heshan.net" />
          </Link>
          <div className="nav-links">
            <Link to="/chat">聊天广场</Link>
            <Link to="/find">寻人信息</Link>
            <AdminLink />
            {auth ? (
              <button className="button button-secondary" type="button" onClick={clearAuth}>
                退出登录
              </button>
            ) : (
              <>
                <Link to="/login">登录</Link>
                <Link to="/register">注册</Link>
              </>
            )}
          </div>
        </nav>

        <div className="hero-grid">
          <section className="hero-copy">
            <p className="eyebrow">heshan.net Community</p>
            <h1>同鹤汇</h1>
            <p className="hero-lede">
              为鹤山旧友、同窗和街坊留下一个安静好用的线上广场。
            </p>
            <div className="hero-actions">
              <Link className="button" to="/chat">进入聊天广场</Link>
              <Link className="button button-secondary" to="/find">查找老朋友</Link>
            </div>
          </section>

          <aside className="hero-panel" aria-label="站点状态">
            <div className="status-row">
              <span className={`status-dot status-${health}`} />
              <span>后端状态</span>
              <strong>{health}</strong>
            </div>
            <div className="feature-list">
              <Link className="feature-link" to="/chat">
                <strong>聊天广场</strong>
                <span>发布近况、话题和留言。</span>
              </Link>
              <Link className="feature-link" to="/find">
                <strong>寻人信息</strong>
                <span>按昵称、地点和年份找回旧识。</span>
              </Link>
              <Link className="feature-link" to="/login">
                <strong>账号系统</strong>
                <span>登录后即可发布帖子和评论。</span>
              </Link>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
