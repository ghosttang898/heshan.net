import { useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { getCurrentUser } from "../../api";
import { clearAuth, getAuth, saveAuth, subscribeAuthChange } from "../../auth";

export default function AdminRoute() {
  const location = useLocation();
  const [token, setToken] = useState(getAuth()?.token);
  const [result, setResult] = useState({ status: "loading" });
  const [retry, setRetry] = useState(0);

  useEffect(() => subscribeAuthChange(() => setToken(getAuth()?.token)), []);
  useEffect(() => {
    if (!token) return;
    let active = true;
    setResult({ status: "loading" });
    getCurrentUser().then(({ data }) => {
      if (!active) return;
      saveAuth({ ...getAuth(), ...data });
      setResult({ status: ["ADMIN", "SUPER_ADMIN"].includes(data.role) ? "ready" : "denied", user: data });
    }).catch((error) => {
      if (!active) return;
      if (error.response?.status === 401) clearAuth();
      setResult({ status: error.response?.status === 403 ? "denied" : "error" });
    });
    return () => { active = false; };
  }, [token, retry, location.state?.recheckPermissions]);

  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (result.status === "ready") return <Outlet context={result.user} />;
  return (
    <main className="admin-access">
      <h1>同鹤汇 heshan.net</h1>
      {result.status === "loading" ? <p role="status">正在验证管理员身份...</p> : result.status === "denied" ? (
        <><h2>403 · 无访问权限</h2><p>此帐号没有后台管理权限。</p><Link to="/">返回首页</Link></>
      ) : <><p role="alert">无法验证身份，请检查网络后重试。</p><button onClick={() => setRetry(retry + 1)}>重试</button></>}
    </main>
  );
}
