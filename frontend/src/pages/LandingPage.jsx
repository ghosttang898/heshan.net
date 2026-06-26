import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getHealth } from "../api";
import { clearAuth, getAuth, subscribeAuthChange } from "../auth";

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
    <main className="page">
      <section className="card">
        <h1>同鹤汇 TongHeHui</h1>
        <p>同鹤汇是一个简洁的社区原型，当前提供聊天信息与寻人信息的基础发布能力。</p>
        <p>
          后端健康状态: <strong>{health}</strong>
        </p>
        <nav className="nav-links">
          <Link to="/chat">聊天广场</Link>
          <Link to="/find">寻人信息</Link>
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
        </nav>
      </section>
    </main>
  );
}
