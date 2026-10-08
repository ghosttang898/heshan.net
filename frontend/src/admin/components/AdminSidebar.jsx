import { NavLink, Link } from "react-router-dom";
import { LayoutDashboard, FileText, MessageSquare, Users, ArrowUpRight, ShieldCheck } from "lucide-react";

const items = [
  ["/admin", "总览", LayoutDashboard],
  ["/admin/posts", "帖子管理", FileText],
  ["/admin/comments", "评论管理", MessageSquare],
  ["/admin/users", "用户管理", Users],
];

export default function AdminSidebar({ user }) {
  const visibleItems = user.role === "SUPER_ADMIN"
    ? [...items, ["/admin/administrators", "管理员管理", ShieldCheck]] : items;
  return (
    <aside className="admin-sidebar">
      <Link to="/admin" className="admin-brand"><strong>同鹤汇 <span>heshan.net</span></strong><small>社区管理</small></Link>
      <nav aria-label="后台导航">
        {visibleItems.map(([to, label, Icon]) => <NavLink key={to} to={to} end={to === "/admin"} title={to === "/admin/administrators" ? "Administrator Management" : label}>
          <Icon size={18} aria-hidden="true" />{label}
        </NavLink>)}
      </nav>
      <div className="admin-sidebar-bottom">
        <Link to="/"><ArrowUpRight size={16} aria-hidden="true" />访问网站</Link>
        <span>heshan.net Admin</span><small>heshan.net</small>
      </div>
    </aside>
  );
}
