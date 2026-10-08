import { Link, useOutletContext } from "react-router-dom";
import AdminResourcePage from "../components/AdminResourcePage";

export default function AdminAdministratorsPage() {
  const user = useOutletContext();
  if (user.role !== "SUPER_ADMIN") return <div className="admin-state"><h1>403 · 无访问权限</h1><p>仅超级管理员可管理授权。</p><Link to="/admin">返回总览</Link></div>;
  return <><div className="admin-management-link"><Link to="/admin/users">前往用户管理</Link></div>
    <AdminResourcePage resource="administrators" title="管理员管理" /></>;
}
