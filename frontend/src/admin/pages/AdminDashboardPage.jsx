import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Users, FileText, MessageSquare, UserPlus, FilePlus, MessagesSquare, RefreshCw, ExternalLink } from "lucide-react";
import { getDashboard } from "../api";
import useAdminError from "../useAdminError";
import StatCard from "../components/StatCard";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { CLOUDFLARE_ANALYTICS_DASHBOARD } from "../../analytics";

const stats = [
  ["totalUsers", "用户总数", Users, "green"], ["totalPosts", "帖子总数", FileText, "blue"],
  ["totalComments", "评论总数", MessageSquare, "rose"], ["todayNewUsers", "今日新增用户", UserPlus, "green"],
  ["todayNewPosts", "今日新增帖子", FilePlus, "blue"], ["todayNewComments", "今日新增评论", MessagesSquare, "rose"],
];

export default function AdminDashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const handleError = useAdminError();
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    getDashboard().then(({ data }) => { if (active) setData(data); })
      .catch((error) => { if (active) setError(handleError(error)); });
    return () => { active = false; };
  }, [refresh]);

  return <>
    <div className="admin-page-heading"><div><h1>社区总览</h1><p>同鹤汇 heshan.net</p></div>
      <button className="admin-icon-button" title="刷新统计" aria-label="刷新统计" onClick={() => setRefresh(refresh + 1)}><RefreshCw size={18} /></button>
    </div>
    <section className="admin-section admin-traffic" aria-labelledby="traffic-title">
      <div><h2 id="traffic-title">网站流量统计</h2><h3>Cloudflare Web Analytics</h3>
        <p>查看公开页面的浏览量、访客趋势和访问来源。</p></div>
      <a className="admin-button admin-traffic-link" href={CLOUDFLARE_ANALYTICS_DASHBOARD} target="_blank" rel="noopener noreferrer">
        查看详细统计<ExternalLink size={16} aria-hidden="true" /></a>
    </section>
    {error ? <p className="admin-error" role="alert">{error}</p> : !data ? <p className="admin-state" role="status">正在加载统计...</p> : <>
      <div className="admin-stats">{stats.map(([key, label, Icon, tone]) => <StatCard key={key} label={label} value={data[key]} Icon={Icon} tone={tone} />)}</div>
      <section className="admin-section"><div className="admin-section-heading"><h2>最近帖子</h2><Link to="/admin/posts">全部帖子</Link></div>
        <DataTable rows={data.recentPosts} columns={[
          { key: "id", label: "ID" }, { key: "title", label: "标题" }, { key: "type", label: "类型", render: (row) => row.type === "CHAT" ? "聊天广场" : "寻人信息" },
          { key: "status", label: "状态", render: (row) => <StatusBadge status={row.status} /> },
          { key: "createdAt", label: "发表时间", render: (row) => new Date(row.createdAt).toLocaleString() },
        ]} />
      </section>
      <section className="admin-section"><div className="admin-section-heading"><h2>最近用户</h2><Link to="/admin/users">全部用户</Link></div>
        <DataTable rows={data.recentUsers} columns={[
          { key: "id", label: "ID" }, { key: "username", label: "帐号" }, { key: "displayName", label: "显示名" },
          { key: "role", label: "角色" }, { key: "createdAt", label: "注册时间", render: (row) => new Date(row.createdAt).toLocaleString() },
        ]} />
      </section>
    </>}
  </>;
}
