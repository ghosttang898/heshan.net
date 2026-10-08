import { LogOut } from "lucide-react";
import { clearAuth } from "../../auth";
import { formatUserName } from "../../userName";

export default function AdminHeader({ user }) {
  return <header className="admin-header">
    <span>同鹤汇 / 管理工作台</span>
    <div><span className="admin-role">{user.role}</span><span>{formatUserName(user.displayName, user.username)}</span>
      <button className="admin-icon-button" onClick={clearAuth} title="退出登录" aria-label="退出登录"><LogOut size={18} /></button>
    </div>
  </header>;
}
